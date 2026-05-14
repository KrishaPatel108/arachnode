import random


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


class RotateUserAgentMiddleware:
    def process_request(self, request, spider):
        request.headers["User-Agent"] = random.choice(USER_AGENTS)

import logging
import time
import redis
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message

logger = logging.getLogger(__name__)


class ExponentialBackoffRetryMiddleware(RetryMiddleware):
    """
    Extends Scrapy's built-in RetryMiddleware with:
    - Exponential backoff delay between retries (2^attempt seconds)
    - Logs dropped URLs to Redis key 'arachnode:failed_urls' on exhaustion
    """

    def __init__(self, settings):
        super().__init__(settings)
        self.failed_urls_key = settings.get("FAILED_URLS_KEY", "arachnode:failed_urls")
        self.redis_client = redis.Redis(
            host=settings.get("REDIS_HOST", "localhost"),
            port=settings.getint("REDIS_PORT", 6379),
            decode_responses=True,
        )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):
        if request.meta.get("dont_retry", False):
            return response
        if response.status in self.retry_http_codes:
            retry_count = request.meta.get("retry_times", 0)
            reason = response_status_message(response.status)
            return self._retry_or_drop(request, reason, retry_count, spider) or response
        return response

    def process_exception(self, request, exception, spider):
        if isinstance(exception, self.EXCEPTIONS_TO_RETRY) and not request.meta.get("dont_retry", False):
            retry_count = request.meta.get("retry_times", 0)
            return self._retry_or_drop(request, exception, retry_count, spider)

    def _retry_or_drop(self, request, reason, retry_count, spider):
        if retry_count < self.max_retry_times:
            delay = 2 ** retry_count  # 1s, 2s, 4s
            logger.warning(
                "[Retry] %s failed (%s). Attempt %d/%d — backing off %ds.",
                request.url, reason, retry_count + 1, self.max_retry_times, delay,
            )
            time.sleep(delay)
            return self.retry(request, reason, spider)
        else:
            logger.error(
                "[Retry] Dropping %s after %d attempts (%s). Logged to Redis key '%s'.",
                request.url, self.max_retry_times, reason, self.failed_urls_key,
            )
            self.redis_client.lpush(
                self.failed_urls_key,
                f"{request.url} | {reason} | {time.strftime('%Y-%m-%dT%H:%M:%S')}",
            )
            return None