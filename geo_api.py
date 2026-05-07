import aiohttp
import asyncio


async def get_geo_data(business_type: str, lat: float, lon: float, radius: int = 1500) -> dict:
    overpass_urls = [
        "http://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]

    # 1. Базовые теги для ВСЕХ типов бизнеса (Жилье и Транспорт)
    query_parts = [
        f'nwr["building"~"apartments|residential"](around:{radius},{lat},{lon});',
        f'nwr["highway"="bus_stop"](around:{radius},{lat},{lon});',
        f'nwr["station"="subway"](around:{radius},{lat},{lon});'
    ]

    # 2. Добавляем специфичные теги в зависимости от выбора
    if business_type == "pharmacy":
        query_parts.extend([
            f'nwr["amenity"~"hospital|clinic|doctors"](around:{radius},{lat},{lon});',
            f'nwr["shop"~"supermarket|convenience"](around:{radius},{lat},{lon});',
            f'nwr["amenity"="pharmacy"](around:{radius},{lat},{lon});'  # Конкуренты
        ])
    elif business_type == "cafe":
        query_parts.extend([
            f'nwr["building"~"commercial|office"](around:{radius},{lat},{lon});',
            f'nwr["office"](around:{radius},{lat},{lon});',
            f'nwr["amenity"~"university|college"](around:{radius},{lat},{lon});',
            f'nwr["leisure"="park"](around:{radius},{lat},{lon});',
            f'nwr["amenity"~"cafe|fast_food"](around:{radius},{lat},{lon});',  # Конкуренты
            f'nwr["shop"="bakery"](around:{radius},{lat},{lon});'  # Тоже конкуренты
        ])
    elif business_type == "pvz":
        query_parts.extend([
            f'nwr["shop"="outpost"](around:{radius},{lat},{lon});'  # Конкуренты ПВЗ
        ])

    # Склеиваем всё в один большой запрос к базе карт
    overpass_query = "[out:json];\n(\n" + "\n".join(query_parts) + "\n);\nout center;"

    headers = {"User-Agent": "Luntara_testbot_v4 / Educational Project"}
    timeout = aiohttp.ClientTimeout(total=25)  # Увеличили таймаут, так как запрос тяжелый

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for url in overpass_urls:
            try:
                print(f"Запрашиваю данные с {url}...")
                async with session.post(url, data={'data': overpass_query}) as response:
                    if response.status == 200:
                        data = await response.json()
                        elements = data.get('elements', [])

                        # 3. Подготавливаем словарь для сортировки результатов
                        result = {
                            "residential": [], "transport": [], "medical": [],
                            "supermarkets": [], "offices": [], "education": [],
                            "parks": [], "competitors": []
                        }

                        # 4. Сортируем полученные объекты по категориям
                        for el in elements:
                            tags = el.get('tags', {})

                            if tags.get('building') in ['apartments', 'residential']:
                                result["residential"].append(el)
                            elif tags.get('highway') == 'bus_stop' or tags.get('station') == 'subway':
                                result["transport"].append(el)
                            elif tags.get('amenity') in ['hospital', 'clinic', 'doctors']:
                                result["medical"].append(el)
                            elif tags.get('shop') in ['supermarket', 'convenience']:
                                result["supermarkets"].append(el)
                            elif tags.get('building') in ['commercial', 'office'] or 'office' in tags:
                                result["offices"].append(el)
                            elif tags.get('amenity') in ['university', 'college']:
                                result["education"].append(el)
                            elif tags.get('leisure') == 'park':
                                result["parks"].append(el)

                            # Сортировка конкурентов в зависимости от бизнеса
                            elif business_type == "pharmacy" and tags.get('amenity') == 'pharmacy':
                                result["competitors"].append(el)
                            elif business_type == "cafe" and (
                                    tags.get('amenity') in ['cafe', 'fast_food'] or tags.get('shop') == 'bakery'):
                                result["competitors"].append(el)
                            elif business_type == "pvz" and tags.get('shop') == 'outpost':
                                result["competitors"].append(el)

                        return result
            except asyncio.TimeoutError:
                print(f"Таймаут {url}. Следующий...")
            except Exception as e:
                print(f"Ошибка {url}: {e}")

    return None