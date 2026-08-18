# Добавьте повторные попытки для проблемных источников
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry_strategy = Retry(
    total=2,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=30, pool_maxsize=30)
session.mount('http://', adapter)
session.mount('https://', adapter)