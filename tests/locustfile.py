import random
from locust import HttpUser, between, task


# ссылки которые будем сокращать
SAMPLE_URLS = [
    "https://www.wildberries.ru/catalog/elektronika",
    "https://www.ozon.ru/category/smartfony-15502/",
    "https://www.avito.ru/moskva/telefony",
    "https://market.yandex.ru/catalog--noutbuki/54544",
    "https://vk.com/feed",
    "https://ok.ru/feed",
    "https://www.dns-shop.ru/catalog/17a8a01d16404e77/noutbuki/",
    "https://www.lamoda.ru/c/477/clothes-muzhskaya-odezhda/",
]


class RegularUser(HttpUser):
    """
    Обычный юзер - создает ссылки и иногда переходит по ним.
    позволяет оценить базовую нагрузку без эффекта кэша.
    каждый раз создается новая ссылка, так что кэш почти не помогает
    """
    wait_time = between(0.5, 2)

    def on_start(self):
        # при старте создаем первую ссылку
        self.short_code = self._create_link()

    def _create_link(self):
        url = random.choice(SAMPLE_URLS)
        resp = self.client.post(
            "/links/shorten",
            json={"original_url": url},
            name="/links/shorten",
        )
        if resp.status_code == 201:
            return resp.json()["short_code"]
        return None

    @task(3)
    def create_new_link(self):
        # массовое создание ссылок
        code = self._create_link()
        if code:
            self.short_code = code

    @task(5)
    def access_link(self):
        # переходим по ссылке - первый раз идет в бд, потом из кэша
        if self.short_code:
            self.client.get(
                f"/links/{self.short_code}",
                allow_redirects=False,
                name="/links/[short_code]",
            )

    @task(2)
    def get_stats(self):
        if self.short_code:
            self.client.get(
                f"/links/{self.short_code}/stats",
                name="/links/[short_code]/stats",
            )

    @task(1)
    def search_by_url(self):
        url = random.choice(SAMPLE_URLS)
        self.client.get(
            "/links/search",
            params={"original_url": url},
            name="/links/search",
        )

class CachedUser(HttpUser):
    """
    Юзер который долбит одну и ту же ссылку много раз.
    нужен чтоб оценить влияние кэша - после первого запроса
    все последующие редиректы идут из redis, а не из бд.
    Сравниваем rps и latency с RegularUser чтоб понять профит от кэша.
    """
    wait_time = between(0.1, 0.5)

    def on_start(self):
        # создаем одну ссылку на весь тест
        resp = self.client.post(
            "/links/shorten",
            json={"original_url": "https://www.wildberries.ru/catalog/elektronika"},
            name="/links/shorten",
        )
        if resp.status_code == 201:
            self.short_code = resp.json()["short_code"]
        else:
            self.short_code = None

    @task(8)
    def access_same_link_repeatedly(self):
        # повторные обращения - работает кэш
        if self.short_code:
            self.client.get(
                f"/links/{self.short_code}",
                allow_redirects=False,
                name="/links/[short_code] (cached)",
            )

    @task(2)
    def get_stats_cached(self):
        # статистика тоже кэшируется
        if self.short_code:
            self.client.get(
                f"/links/{self.short_code}/stats",
                name="/links/[short_code]/stats (cached)",
            )
