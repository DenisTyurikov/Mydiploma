import requests
import time
import pandas as pd
import h3

# 1. Настройка точек сканирования
# Указываем координаты центров разных районов города.
# Радиус будет большим (например, 3 км), поэтому круги будут пересекаться.
SCAN_POINTS = [
    {"lat": 51.66465, "lon": 39.191269, "name": "Центр"},
    {"lat": 51.69850, "lon": 39.176200, "name": "Северный район"},
    {"lat": 51.62580, "lon": 39.255500, "name": "Левый берег (Юг)"},
    {"lat": 51.67780, "lon": 39.263800, "name": "Левый берег (Север)"},
    {"lat": 51.63660, "lon": 39.170600, "name": "Юго-Западный"}
]
RADIUS = 3000  # 3 км вокруг каждой точки


def fetch_osm_data(lat, lon, radius):
    """Отправляет запрос к Overpass API для одной точки."""
    overpass_url = "http://overpass-api.de/api/interpreter"

    # Собираем абсолютно все нужные нам теги за один проход
    query = f"""
    [out:json];
    (
      nwr["building"~"apartments|residential"](around:{radius},{lat},{lon});
      nwr["highway"="bus_stop"](around:{radius},{lat},{lon});
      nwr["station"="subway"](around:{radius},{lat},{lon});
      nwr["amenity"~"hospital|clinic|doctors"](around:{radius},{lat},{lon});
      nwr["shop"~"supermarket|convenience"](around:{radius},{lat},{lon});
      nwr["building"~"commercial|office"](around:{radius},{lat},{lon});
      nwr["office"](around:{radius},{lat},{lon});
      nwr["amenity"~"university|college"](around:{radius},{lat},{lon});
      nwr["leisure"="park"](around:{radius},{lat},{lon});
      nwr["amenity"~"pharmacy|cafe|fast_food"](around:{radius},{lat},{lon});
      nwr["shop"~"bakery|outpost"](around:{radius},{lat},{lon});
    );
    out center;
    """

    headers = {"User-Agent": "Diploma Project / Real Data Vacuum"}

    try:
        response = requests.post(overpass_url, data={'data': query}, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json().get('elements', [])
        else:
            print(f"Ошибка {response.status_code}")
            return []
    except Exception as e:
        print(f"Сетевая ошибка: {e}")
        return []


def process_city():
    print("🚀 Запуск сбора реальных геоданных...\n")

    # Словари для хранения глобальных данных
    # seen_ids нужен, чтобы не посчитать один и тот же дом дважды на стыке районов
    seen_ids = set()

    # Главный словарь гексагонов всего города
    city_hex_data = {}

    for point in SCAN_POINTS:
        print(f"📡 Сканирую зону: {point['name']} (lat: {point['lat']}, lon: {point['lon']})")

        elements = fetch_osm_data(point['lat'], point['lon'], RADIUS)
        print(f"   Найдено сырых объектов: {len(elements)}")

        added_new = 0
        for el in elements:
            obj_id = el.get('id')
            if obj_id in seen_ids:
                continue  # Пропускаем, если уже находили этот объект в другом районе

            seen_ids.add(obj_id)
            added_new += 1

            # Определяем координаты объекта
            i_lat = el.get('center', {}).get('lat') or el.get('lat')
            i_lon = el.get('center', {}).get('lon') or el.get('lon')

            if not (i_lat and i_lon):
                continue

            # Вычисляем гексагон
            try:
                h_id = h3.latlng_to_cell(i_lat, i_lon, 9)
            except AttributeError:
                h_id = h3.geo_to_h3(i_lat, i_lon, 9)

            # Инициализируем гексагон, если его еще нет
            if h_id not in city_hex_data:
                city_hex_data[h_id] = {
                    "residential": 0, "transport": 0, "medical": 0,
                    "supermarkets": 0, "offices": 0, "education": 0,
                    "parks": 0, "pharmacy_comp": 0, "cafe_comp": 0, "pvz_comp": 0
                }

            # Сортируем объект по категориям
            tags = el.get('tags', {})
            if tags.get('building') in ['apartments', 'residential']:
                city_hex_data[h_id]["residential"] += 1
            elif tags.get('highway') == 'bus_stop' or tags.get('station') == 'subway':
                city_hex_data[h_id]["transport"] += 1
            elif tags.get('amenity') in ['hospital', 'clinic', 'doctors']:
                city_hex_data[h_id]["medical"] += 1
            elif tags.get('shop') in ['supermarket', 'convenience']:
                city_hex_data[h_id]["supermarkets"] += 1
            elif tags.get('building') in ['commercial', 'office'] or 'office' in tags:
                city_hex_data[h_id]["offices"] += 1
            elif tags.get('amenity') in ['university', 'college']:
                city_hex_data[h_id]["education"] += 1
            elif tags.get('leisure') == 'park':
                city_hex_data[h_id]["parks"] += 1

            # Конкуренты сортируются отдельно, так как мы собираем базу для всех сразу
            elif tags.get('amenity') == 'pharmacy':
                city_hex_data[h_id]["pharmacy_comp"] += 1
            elif tags.get('amenity') in ['cafe', 'fast_food'] or tags.get('shop') == 'bakery':
                city_hex_data[h_id]["cafe_comp"] += 1
            elif tags.get('shop') == 'outpost':
                city_hex_data[h_id]["pvz_comp"] += 1

        print(f"   Новых уникальных объектов добавлено: {added_new}")

        # Засыпаем на 30 секунд перед следующим запросом, чтобы сервер нас не заблокировал
        print("   Ожидание 30 секунд (защита от бана API)...\n")
        time.sleep(30)

    # Сохранение итогового результата
    print(f"🏆 Сбор завершен! Всего сформировано уникальных гексагонов: {len(city_hex_data)}")

    data_for_df = []
    for h_id, stats in city_hex_data.items():
        row = {'hex_id': h_id}
        row.update(stats)
        data_for_df.append(row)

    df = pd.DataFrame(data_for_df)
    df.to_csv("real_city_dataset.csv", index=False)
    print("💾 Данные сохранены в файл 'real_city_dataset.csv'")


if __name__ == "__main__":
    process_city()