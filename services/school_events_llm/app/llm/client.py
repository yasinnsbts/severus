"""Model Router и адаптеры LLM (ТЗ 4). Только стандартная библиотека (urllib).

Смена модели - через ACTIVE_MODEL в .env и config/models.json, без правок генератора.
Тихого переключения на другую модель нет (fallback.enabled=false).
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .jsonx import strip_reasoning
from .limits import SlotTimeout, llm_request_slot
from .mutex import local_llm_lock


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False, retry_after: float | None = None):
        """Сохраняет стабильный код ошибки LLM, сообщение и признак допустимости повторной попытки.

        Параметры:
            `code`, `message`, `retryable`;
            `retry_after` - сколько секунд просит подождать провайдер (заголовок `Retry-After` ответа 429).
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass
class LLMResult:
    text: str
    model_key: str
    provider: str
    provider_model_id: str
    usage: dict[str, Any] | None
    latency_ms: int
    mutex_wait_ms: int = 0
    reasoning_stripped: bool = False
    structured_mode: str = "none"
    request_params: dict[str, Any] = field(default_factory=dict)
    # Рассуждения модели (`reasoning_content` в ответе): пишутся в трассу отдельно, в разбор JSON не попадают.
    reasoning: str | None = None


class LLMClient:
    model_key: str = "base"
    provider: str = "base"
    # Можно ли генерировать варианты одной задачи одновременно. Клиенты, которые отвечают записанными
    # ответами по порядку вызовов (повтор трасс в тестах), ставят False: при параллельных вариантах порядок другой.
    parallel_variants_safe: bool = True

    def generate(self, *, messages: list[dict[str, str]], task_name: str, output_schema: dict | None,
                 max_tokens: int, temperature: float, meta: dict[str, Any] | None = None) -> LLMResult:
        """Отправляет сообщения модели, применяет локальную очередь, обрабатывает structured output и возвращает нормализованный результат.

        Параметры:
            `messages`, `task_name`, `output_schema`, `max_tokens`, `temperature`, `meta`.

        Возвращает:
            LLMResult.
        """
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        """Проверяет доступность провайдера и возвращает диагностические сведения о модели.

        Возвращает:
            dict[str, Any].
        """
        raise NotImplementedError


def _is_local(url: str) -> bool:
    """Определяет, указывает ли URL на локальный хост.

    Параметры:
        `url`.

    Возвращает:
        bool.
    """
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None,
               timeout: float = 60, form: dict[str, str] | None = None) -> tuple[int, Any]:
    """Выполняет HTTP-запрос и возвращает код ответа и разобранный JSON без использования системного прокси для localhost.

    Параметры:
        `url`, `method`, `body`, `headers`, `timeout`, `form`.

    Возвращает:
        tuple[int, Any].
    """
    data = None
    hdrs = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if form is not None:
        data = "&".join(f"{k}={v}" for k, v in form.items()).encode("utf-8")
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if _is_local(url) else urllib.request.build_opener()
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:2000]}
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after and isinstance(payload, dict):
            payload["_retry_after"] = retry_after
        return exc.code, payload
    except (socket.timeout, TimeoutError) as exc:
        raise LLMError("MODEL_TIMEOUT", f"Истекло время ожидания модели ({timeout} с)", retryable=True) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise LLMError("MODEL_TIMEOUT", f"Истекло время ожидания модели ({timeout} с)", retryable=True) from exc
        raise LLMError("MODEL_UNAVAILABLE", f"Модель недоступна: {exc.reason}", retryable=True) from exc


def _raise_for_status(status: int, payload: Any) -> None:
    """Преобразует HTTP-статус провайдера в стабильную ошибку LLMError.

    Параметры:
        `status`, `payload`.

    Возвращает:
        None.
    """
    if status < 400:
        return
    text = json.dumps(payload, ensure_ascii=False)[:500]
    if status in (401, 403):
        raise LLMError("MODEL_AUTH_ERROR", f"Ошибка авторизации у провайдера ({status})")
    if status == 429:
        # Текст шлюза говорит, какой лимит сработал (запросов или токенов в минуту, одновременных запросов).
        detail = ""
        if isinstance(payload, dict):
            error = payload.get("error")
            detail = str((error.get("message") if isinstance(error, dict) else error) or payload.get("message") or payload.get("raw") or "")
        detail = " ".join(detail.split())[:300]
        retry_after = None
        if isinstance(payload, dict) and payload.get("_retry_after") is not None:
            try:
                retry_after = float(payload["_retry_after"])
            except (TypeError, ValueError):
                retry_after = None
        message = "Превышен лимит запросов провайдера" + (f": {detail}" if detail else "")
        raise LLMError("RATE_LIMITED", message, retryable=True, retry_after=retry_after)
    if status >= 500:
        raise LLMError("MODEL_UNAVAILABLE", f"Ошибка сервера модели ({status}): {text}", retryable=True)
    raise LLMError("MODEL_ERROR", f"Модель отклонила запрос ({status}): {text}")


def strict_schema(schema: dict) -> dict:
    """additionalProperties=false для всех объектов (лучше работает грамматика структурированного вывода)."""
    def walk(node: Any) -> Any:
        """Рекурсивно преобразует вложенную структуру JSON Schema.

        Параметры:
            `node`.

        Возвращает:
            Any.
        """
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key == "title" and isinstance(value, str):
                continue  # служебная подпись схемы, а не поле данных
            if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
                result[key] = {name: walk(sub) for name, sub in value.items()}  # имена полей не трогаем
            else:
                result[key] = walk(value)
        if result.get("type") == "object" and "properties" in result:
            result.setdefault("additionalProperties", False)
        return result
    return walk(schema)


class OpenAICompatibleClient(LLMClient):
    """LM Studio, удалённый Qwen-сервер, OpenAI - через /chat/completions."""

    def __init__(self, model_key: str, cfg: dict[str, Any], api_key: str | None, lock_cfg: dict | None):
        """Настраивает OpenAI-совместимый клиент по записи модели, ключу API и параметрам локальной блокировки.

        Параметры:
            `model_key`, `cfg`, `api_key`, `lock_cfg`.
        """
        self.model_key = model_key
        self.cfg = cfg
        self.provider = cfg.get("provider", "openai_compatible")
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        if not self.base_url:
            raise LLMError("MODEL_UNAVAILABLE", f"Для модели {model_key} не задан base_url в config/models.json")
        self.api_key = api_key
        self.timeout = float(cfg.get("timeout_seconds", 240))
        self.structured_mode = cfg.get("structured_output_mode", "auto")
        self.reasoning_mode = cfg.get("reasoning_mode", "disabled")
        self.thinking_method = cfg.get("disable_thinking_method", "strip_only")
        # Уровень рассуждений по умолчанию для модели (`low` / `medium` / `high`); этап может задать свой через meta.
        self.reasoning_effort = cfg.get("reasoning_effort")
        self._reasoning_param_unsupported = False
        self.local = bool(cfg.get("local", _is_local(self.base_url)))
        self.lock_cfg = lock_cfg if self.local else None
        self._model_id: str | None = None
        self._schema_unsupported = False
        # Шлюз LiteLLM отдаёт сохранённый ответ на запрос, совпадающий до символа. Чтобы каждая генерация
        # и каждое исправление получали новый ответ модели, кэш обходится (config/service.json: llm_cache_bypass).
        self.cache_bypass = bool(cfg.get("gateway_cache")) and bool(cfg.get("cache_bypass", True))
        self._cache_param_unsupported = False

    def _headers(self) -> dict[str, str]:
        """Формирует HTTP-заголовки авторизации для текущего LLM-провайдера.

        Возвращает:
            dict[str, str].
        """
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def list_models(self) -> list[str]:
        """Получает список моделей, доступных на OpenAI-совместимом endpoint.

        Возвращает:
            list[str].
        """
        status, payload = _http_json(f"{self.base_url}/models", headers=self._headers(), timeout=15)
        _raise_for_status(status, payload)
        return [m.get("id") for m in (payload or {}).get("data", []) if m.get("id")]

    def model_id(self) -> str:
        """Определяет фактический идентификатор модели с учётом auto_loaded.

        Возвращает:
            str.
        """
        if self._model_id:
            return self._model_id
        configured = self.cfg.get("model_id")
        if configured and configured not in ("auto_loaded", "SET_ACTUAL_SERVER_MODEL_ID"):
            self._model_id = configured
            return configured
        if configured == "SET_ACTUAL_SERVER_MODEL_ID":
            raise LLMError("MODEL_UNAVAILABLE", f"Для {self.model_key} не указан реальный model_id сервера")
        models = [m for m in self.list_models() if "embed" not in m.lower()]
        if len(models) == 1:
            self._model_id = models[0]
            return models[0]
        if not models:
            raise LLMError("MODEL_UNAVAILABLE", "LM Studio не сообщает ни одной загруженной модели - загрузите модель")
        raise LLMError("MODEL_UNAVAILABLE", "В LM Studio доступно несколько моделей: укажите model_id явно в config/models.json: " + ", ".join(models))

    def health(self) -> dict[str, Any]:
        """Проверяет доступность провайдера и возвращает диагностические сведения о модели.

        Возвращает:
            dict[str, Any].
        """
        return {"model_key": self.model_key, "provider": self.provider, "base_url": self.base_url,
                "models": self.list_models(), "selected_model_id": self.model_id()}

    def _body(self, messages, model_id, max_tokens, temperature, schema, mode, meta=None) -> dict:
        """Собирает тело OpenAI-совместимого запроса с настройками вывода и reasoning_mode.

        Параметры:
            `messages`, `model_id`, `max_tokens`, `temperature`, `schema`, `mode`;
            `meta` - `job_id` и `call_id` вызова: для обхода кэша шлюза.

        Возвращает:
            dict.
        """
        msgs = [dict(m) for m in messages]
        body: dict[str, Any] = {"model": model_id, "messages": msgs, "temperature": temperature,
                                "max_tokens": max_tokens, "stream": False}
        if self.cache_bypass:
            # Два способа сразу: параметр LiteLLM «не читать и не сохранять кэш» и служебная отметка вызова
            # в конце запроса - она делает каждый запрос уникальным, даже если шлюз параметр не учитывает.
            if not self._cache_param_unsupported:
                body["cache"] = {"no-cache": True, "no-store": True}
            marker = "/".join(str((meta or {}).get(k)) for k in ("job_id", "call_id") if (meta or {}).get(k))
            if marker:
                msgs[-1]["content"] = msgs[-1]["content"] + f"\n\n<!-- служебная отметка вызова {marker}, на ответ не влияет -->"
        effort = (meta or {}).get("reasoning_effort") or self.reasoning_effort
        if effort and effort != "none" and self.reasoning_mode != "disabled" and not self._reasoning_param_unsupported:
            # GigaChat API (OpenAI-совместимый формат) и шлюз LiteLLM УрФУ принимают параметр как есть (проверено 14.11).
            body["reasoning_effort"] = effort
        if self.reasoning_mode == "disabled":
            if self.thinking_method == "no_think_tag":
                msgs[-1]["content"] = msgs[-1]["content"] + "\n\n/no_think"
            elif self.thinking_method == "chat_template_kwargs":
                body["chat_template_kwargs"] = {"enable_thinking": False}
        if mode == "json_schema" and schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "stage_output", "strict": True, "schema": strict_schema(schema)}}
        elif mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    def _call(self, body: dict) -> tuple[int, Any]:
        """Отправляет один HTTP-запрос к endpoint генерации модели.

        Параметры:
            `body`.

        Возвращает:
            tuple[int, Any].
        """
        return _http_json(f"{self.base_url}/chat/completions", method="POST", body=body,
                          headers=self._headers(), timeout=self.timeout)

    def generate(self, *, messages, task_name, output_schema, max_tokens, temperature, meta=None) -> LLMResult:
        """Отправляет сообщения модели, применяет локальную очередь, обрабатывает structured output и возвращает нормализованный результат.

        Параметры:
            `messages`, `task_name`, `output_schema`, `max_tokens`, `temperature`, `meta`.

        Возвращает:
            LLMResult.
        """
        model_id = self.model_id()
        mode = self.structured_mode
        if mode == "auto":
            mode = "none" if self._schema_unsupported or not output_schema else "json_schema"
        body = self._body(messages, model_id, max_tokens, temperature, output_schema, mode, meta)

        def do_call() -> tuple[int, Any, int]:
            """Выполняет один OpenAI-совместимый запрос внутри локальной очереди и возвращает нормализованный результат.

            Возвращает:
                tuple[int, Any, int].
            """
            started = time.monotonic()
            status, payload = self._call(body)
            return status, payload, int((time.monotonic() - started) * 1000)

        def call_with_fallback() -> tuple[int, Any, int]:
            """Вызов модели; если провайдер не принял JSON-схему или параметр кэша, повтор без них."""
            nonlocal mode
            status, payload, latency = do_call()
            # 400 на параметр рассуждений: по тексту ошибки, иначе отключили бы обход кэша зря.
            if status == 400 and "reasoning_effort" in body and "reason" in str(payload).lower():
                self._reasoning_param_unsupported = True
                body.pop("reasoning_effort", None)
                status, payload, latency = do_call()
            if status == 400 and "cache" in body:
                # Шлюз не знает параметр кэша: дальше без него, уникальность запроса держит служебная отметка.
                self._cache_param_unsupported = True
                body.pop("cache", None)
                status, payload, latency = do_call()
            if status == 400 and "reasoning_effort" in body:
                # Модель или шлюз не знают параметр рассуждений: дальше без него, генерация не падает.
                self._reasoning_param_unsupported = True
                body.pop("reasoning_effort", None)
                status, payload, latency = do_call()
            if status == 400 and mode == "json_schema" and self.structured_mode == "auto":
                self._schema_unsupported = True
                mode = "none"
                body.pop("response_format", None)
                status, payload, latency = do_call()
            return status, payload, latency

        # Место для обращения к модели: общий предел процесса и предел локальной модели (config/service.json).
        try:
            with llm_request_slot(local=self.local) as slot_wait_ms:
                if self.lock_cfg:
                    with local_llm_lock(**self.lock_cfg) as info:
                        wait_ms = slot_wait_ms + info.get("wait_ms", 0)
                        status, payload, latency = call_with_fallback()
                else:
                    wait_ms = slot_wait_ms
                    status, payload, latency = call_with_fallback()
        except SlotTimeout as exc:
            raise LLMError("SERVICE_BUSY", f"Сервис перегружен: {exc}", retryable=True) from exc
        _raise_for_status(status, payload)
        try:
            message = payload["choices"][0]["message"]
            text = message.get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("OUTPUT_SCHEMA_INVALID", "Неожиданный формат ответа провайдера") from exc
        text, had_reasoning = strip_reasoning(text)
        usage = payload.get("usage")
        return LLMResult(text=text, model_key=self.model_key, provider=self.provider, provider_model_id=model_id,
                         usage=usage, latency_ms=latency, mutex_wait_ms=wait_ms,
                         reasoning_stripped=had_reasoning or bool(message.get("reasoning_content")),
                         structured_mode=mode, reasoning=message.get("reasoning_content") or None,
                         request_params={"temperature": temperature, "max_tokens": max_tokens, "structured_mode": mode,
                                         "reasoning_effort": body.get("reasoning_effort")})


class GigaChatClient(OpenAICompatibleClient):
    """GigaChat: OAuth-токен по ключу авторизации (живёт 30 минут), затем /v1/chat/completions.

    Прототип: проверяется smoke-тестом с реальным ключом (ТЗ 27). Структурированный вывод не используется.
    """

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    def __init__(self, model_key, cfg, auth_key, scope="GIGACHAT_API_PERS"):
        """Настраивает клиент GigaChat, параметры OAuth, модель и таймауты из конфигурации.

        Параметры:
            `model_key`, `cfg`, `auth_key`, `scope`.
        """
        super().__init__(model_key, {**cfg, "structured_output_mode": "none", "local": False}, None, None)
        if not self.base_url.endswith("/v1"):
            self.base_url = self.base_url + "/v1"
        self.auth_key = auth_key
        self.scope = scope
        self._token: str | None = None
        self._token_expires = 0.0

    def _headers(self) -> dict[str, str]:
        """Формирует HTTP-заголовки авторизации для текущего LLM-провайдера.

        Возвращает:
            dict[str, str].
        """
        now = time.time()
        if not self._token or now > self._token_expires - 60:
            if not self.auth_key:
                raise LLMError("MODEL_AUTH_ERROR", "Не задан GIGACHAT_AUTH_KEY")
            status, payload = _http_json(self.OAUTH_URL, method="POST", form={"scope": self.scope},
                                         headers={"Authorization": f"Basic {self.auth_key}", "RqUID": str(uuid.uuid4())},
                                         timeout=30)
            _raise_for_status(status, payload)
            self._token = payload["access_token"]
            self._token_expires = payload.get("expires_at", (now + 1800) * 1000) / 1000
        return {"Authorization": f"Bearer {self._token}"}

    def model_id(self) -> str:
        """Определяет фактический идентификатор модели с учётом auto_loaded.

        Возвращает:
            str.
        """
        return self.cfg.get("model_id") or "GigaChat"


def build_client(settings, model_key: str | None = None) -> LLMClient:
    """Создаёт LLM-клиент по ACTIVE_MODEL и config/models.json без тихого fallback.

    Параметры:
        `settings`, `model_key`.

    Возвращает:
        LLMClient.
    """
    from .limits import configure
    from .mutex import lock_from_settings

    service = settings.service()
    configure(service)
    models = settings.models()
    key = settings.active_model_key(model_key)
    raw_cfg = models.get("models", {}).get(key)
    if not raw_cfg:
        raise LLMError("MODEL_UNAVAILABLE", f"Модель {key} не описана в config/models.json")
    cfg = dict(raw_cfg)
    cfg["cache_bypass"] = bool(service.get("llm_cache_bypass", True))
    if not cfg.get("enabled", False):
        raise LLMError("MODEL_UNAVAILABLE", f"Модель {key} выключена (enabled=false) в config/models.json")
    if cfg.get("base_url_env"):
        base_url = settings.get(cfg["base_url_env"], cfg.get("base_url"))
        if not base_url:
            raise LLMError("MODEL_UNAVAILABLE", f"Не задан {cfg.get('base_url_env')}")
        cfg["base_url"] = base_url
    api_key = settings.get(cfg["api_key_env"]) if cfg.get("api_key_env") else None
    provider = cfg.get("provider")
    if cfg.get("api_key_env") and not api_key and not bool(cfg.get("local", False)):
        raise LLMError("MODEL_AUTH_ERROR", f"Не задан {cfg.get('api_key_env')}")
    if provider in ("openai_compatible", "openai"):
        if provider == "openai" and not api_key:
            raise LLMError("MODEL_AUTH_ERROR", f"Не задан {cfg.get('api_key_env')}")
        return OpenAICompatibleClient(key, cfg, api_key, lock_from_settings(settings))
    if provider == "gigachat":
        return GigaChatClient(key, cfg, api_key, settings.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"))
    raise LLMError("MODEL_UNAVAILABLE", f"Неизвестный провайдер {provider}")


__all__ = ["LLMClient", "LLMError", "LLMResult", "OpenAICompatibleClient", "GigaChatClient", "build_client", "strict_schema"]