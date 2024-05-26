import requests
import time
import datetime
import configparser
import json
import re
import subprocess
import os
import pynvml
import pytz


config = configparser.ConfigParser()
with open('config.ini', encoding='utf-8') as f:
    config.read_file(f)
rig_name = config["setting"]["rig_name"]
ip_maner = config["setting"]["ip_maner"]
variables = {
    'port_miner': 'port_miner',
    'temp_gmem_max': 'temp_gmem_max',
    'temp_gmem_min': 'temp_gmem_min',
    'temp_gcore_max': 'temp_gcore_max',
    'temp_gcore_min': 'temp_gcore_min',
    'count_gpu': 'count_gpu',
    'temp_gmem_deviation': 'temp_gmem_deviation',
    'monitoring_interval': 'monitoring_interval',
    'trex_gmem': 'trex_gmem',
    'trex_gcore': 'trex_gcore',
    'trex_fan': 'trex_fan',
    'trex_power': 'trex_power',
}

# Автотюн
active_control=config["setting"]["active_control"]

# стартовые настройки майнера, заданные пользователем
trex_dir=config["setting"]["trex_dir"]
trex_algo=config["setting"]["trex_algo"]
trex_pool=config["setting"]["trex_pool"]
wallet=config["setting"]["wallet"]
worker=config["setting"]["worker"]

# стартовые настройки майнера, заданные автотюном при последнем запуске.
trex_gmem_pool = config["setting"]["trex_gmem_pool"]
trex_gcore_pool = config["setting"]["trex_gcore_pool"]

# настройки бота и чата телеграм
bot_token=config["setting"]["bot_token"]
chat_id=config["setting"]["chat_id"]

# Валидация данных в формате int из файла настроек
for key, value in variables.items():
    try:
        if key == 'port_miner':
            port_miner = int(config["setting"]["port_miner"])
        elif key == 'temp_gmem_max':
            temp_gmem_max = int(config["setting"]["temp_gmem_max"])
        elif key == 'temp_gmem_min':
            temp_gmem_min = int(config["setting"]["temp_gmem_min"])
        elif key == 'temp_gcore_max':
            temp_gcore_max = int(config["setting"]["temp_gcore_max"])
        elif key == 'temp_gcore_min':
            temp_gcore_min = int(config["setting"]["temp_gcore_min"])
        elif key == 'count_gpu':
            count_gpu = int(config["setting"]["count_gpu"])
        elif key == 'temp_gmem_deviation':
            temp_gmem_deviation = int(config["setting"]["temp_gmem_deviation"])
        elif key == 'monitoring_interval':
            monitoring_interval = int(config["setting"]["monitoring_interval"])
        elif key == 'trex_gmem':
             trex_gmem = int(config["setting"]["trex_gmem"])
        elif key == 'trex_gcore':
            trex_gcore = int(config["setting"]["trex_gcore"])
        elif key == 'trex_fan':
            trex_fan = int(config["setting"]["trex_fan"])
        elif key == 'trex_power':
            trex_power = int(config["setting"]["trex_power"])
    except ValueError:
        raise ValueError(f'Ошибка: Переменная {value} должна быть целым числом, проверьте файл настроек!')

# Валидация значения IP-адреса для переменной ip_maner
ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
if not ip_pattern.match(ip_maner):
    raise ValueError('Ошибка: Некорректный формат IP-адреса для переменной ip_maner, проверьте файл настроек!')

# Валидация значения включенного/отключенного автотюна
if active_control.lower() == 'true':
    active_control = True
elif active_control.lower() == 'false':
    active_control = False
else:
    raise ValueError('Переменная active_control должна содержать значение True или False, проверьте файл настроек!')

def autotune_start(usage_string, max_control):
    """Функция валидации значений частот GPU для автотюна"""
    int_list = []
    for value in usage_string.split(','):
        try:
            if int(value.strip()) > max_control:
                raise Exception(f'Значения частот для старта автотюна превышают максимально допустимые значения, указанные в файле настроек.')
            int_list.append(int(value.strip()))
        except ValueError:
            raise Exception(f"Ошибка: Невозможно преобразовать значение '{value.strip()}' в int.")
    return int_list


def format_gmem(list_frequencies):
    """Форматируем частоты памяти GPU для старта майнера"""
    return f"--mclock {','.join(str(value) for value in list_frequencies)}"

def format_gcore(list_frequencies):
    """Форматируем частоты ядер GPU для старта майнера"""
    return f"--lock-cclock {','.join(str(value) for value in list_frequencies)}"

def format_gmem_default(num_gpu, trex_gmem):
    """Форматируем скорость вентилятора для старта майнера"""
    gmem_speeds = [trex_gmem - 300 for _ in range(num_gpu)]
    list_frequencies = [str(speed) for speed in gmem_speeds]
    return f"--mclock {','.join(list_frequencies)}"

def format_gcore_default(num_gpu, trex_gmem):
    """Частоты ядер GPU для старта майнера по умолчанию"""
    gcore_speeds = [trex_gmem - 150 for _ in range(num_gpu)]
    list_frequencies = [str(speed) for speed in gcore_speeds]
    return f"--lock-cclock {','.join(list_frequencies)}"

def format_fan_speed(pieces, ob_fan):
    """Форматируем скорость вентилятора для старта майнера"""
    fan_speeds = [ob_fan] * pieces
    return f"--fan {','.join(str(speed) for speed in fan_speeds)}"


def power_limit(pieces, power_limit):
    """Форматируем power limit для старта майнера"""
    pw_limit = [power_limit] * pieces
    return f"--pl {','.join(str(speed) for speed in pw_limit)}"

def checker_trex_process():
    """Функция проверки запущен ли процесс t-rex.exe"""
    try:
        cmd_processes = subprocess.check_output("tasklist /FI \"IMAGENAME eq t-rex.exe\" /FO CSV", shell=True).decode('cp866')
    except UnicodeDecodeError:
        try:
            cmd_processes = subprocess.check_output("tasklist /FI \"IMAGENAME eq t-rex.exe\" /FO CSV", shell=True).decode('cp437')
        except UnicodeDecodeError:
            print("Не удалось декодировать вывод команды tasklist.")
            return
    return cmd_processes.strip().split('\r\n')


def tg_alert(alarm):
    """Функция отправки сообщения в чат через бота telegram"""
    return requests.get(f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&parse_mode=html&text={alarm}')


def start_trex_process(speed_fan, speed_gmem, speed_gcore, power_limit):
    """Функция старта процесса t-rex.exe с заданными параметрами"""
    trex_custom = f'{trex_dir} -a {trex_algo} --api-bind-http 0.0.0.0:{port_miner} {speed_fan} {speed_gcore} {speed_gmem} {power_limit}  -o {trex_pool} -u {wallet}.{worker} -p x'
    return subprocess.Popen(['cmd', '/c', 'start', 'cmd', '/k', trex_custom], shell=True)


def check_api_temp(funk, api_temp):
    """Функция валидации значений температур GPU, полученных с api"""
    try:
        meaning = int(funk.get(api_temp, 0))
    except (ValueError, TypeError):
        meaning = 0
    return meaning

def count_video_cards():
    """Функция подсчета NVIDIA видеокарт в pci"""
    try:
        pynvml.nvmlInit()
    except pynvml.NVMLError_LibraryNotFound:
        print("NVIDIA NVML library not found.")
        return 0
    return pynvml.nvmlDeviceGetCount()

def response_api(timeout):
    """Функция обращения к api майнера"""
    url_miner = f"http://{ip_maner}:{port_miner}/summary"
    return requests.get(url_miner, timeout=timeout)

def time_samaran():
    """Функция вывода текущего времени в Самаре"""
    now = datetime.datetime.now(pytz.utc)
    timezone_samaran = pytz.timezone('Europe/Samara')
    now_samaran = now.astimezone(timezone_samaran)
    return now_samaran.strftime("%H:%M:%S %d.%m.%Y")

def extract(data, value):
    """Функция извлечения значений данных из списка словарей"""
    value_list = [str(d.get(value, '')) for d in data]
    return '/'.join(value_list)

def stat_message(time_now, trex_ver, hashrate, data, autotune_gmem_pool, autotune_gcore_pool):
    """Сбор информации для отправки статистики в tg"""
    message = (
        f'Время: {time_now}'
        f'\nМайнер: T-Rex v.{trex_ver}'
        f'\nCFX hashrate: {hashrate} Mh'
        f'\nТемп. памяти: {extract(data, "memory_temperature")}°C'
        f'\nТемп. ядер: {extract(data, "temperature")}°C'
        f'\nЧастоты MEM: {",".join(map(str, autotune_gmem_pool))}'
        f'\nЧастоты CORE: {",".join(map(str, autotune_gcore_pool))}'
        )
    return message

# Валидация значений частот GPU для автотюна
autotune_gmem_pool = autotune_start(trex_gmem_pool, trex_gmem)
autotune_gcore_pool = autotune_start(trex_gcore_pool, trex_gcore)

# Чекаем предварительно колличество видеокарт в pci
num_gpu = count_video_cards()

# Запуск мониторинга, а если он не запущен, то старт t-rex.exe
count_start = 0
while True:
    count_start += 1
    # Проверяем запущен ли процесс t-rex.exe
    trex_process = checker_trex_process()
    if len(trex_process) > 1:
        response = response_api(10)
        if response.status_code == 200:
            json_data = response.json()
            if len(json_data["gpus"]) == count_gpu:
                print('Все видеокарты обнаружены')
                log_gpus = []
                for gpu in json_data["gpus"]:
                    memory_temp = check_api_temp(gpu, "memory_temperature")
                    core_temp = check_api_temp(gpu, "temperature")
                    converted_gpu = {
                        "device_id": gpu.get("device_id", 0),
                        "vendor": gpu.get("vendor", ""),
                        "name": gpu.get("name", ""),
                        "memory_temperature": memory_temp,
                        "temperature": core_temp,
                        "max_mtemp_count": 0,
                        "max_ctemp_count": 0,
                        "min_mtemp_count": 0
                        }
                    log_gpus.append(converted_gpu)
            else:
                alarm = f'Внимание!!! Количество обнаруженных видеокарт в {rig_name} не соответствует заявленному!'
                print(alarm)
                tg_alert(alarm)
                log_gpus = []
                for gpu in json_data["gpus"]:
                    memory_temp = check_api_temp(gpu, "memory_temperature")
                    core_temp = check_api_temp(gpu, "temperature")
                    converted_gpu = {
                        "device_id": gpu.get("device_id", 0),
                        "vendor": gpu.get("vendor", ""),
                        "name": gpu.get("name", ""),
                        "memory_temperature": memory_temp,
                        "temperature": core_temp,
                        "max_mtemp_count": 0,
                        "max_ctemp_count": 0,
                        "min_mtemp_count": 0
                        }
                    log_gpus.append(converted_gpu)
            count_start = 0 # если старт удачный, обновляем счетчик
            break
        else:
            # кикаем процесс и запускаем заново
            print('API майнера не отвечает, перезапускаю t-rex.exe')
            for process in trex_process[1:]:
                parts = process.split('","')
                pid = parts[1].strip('"')
                subprocess.call(f"taskkill /PID {pid} /F", shell=True)
            time.sleep(5)
            start_trex_process(speed_fan=format_fan_speed(num_gpu, trex_fan), speed_gmem=format_gmem(autotune_gmem_pool), speed_gcore=format_gcore(autotune_gcore_pool), power_limit=power_limit(num_gpu, trex_power))
            time.sleep(40)
            continue
    else:
        if count_start == 4:
            raise Exception('Не удалось запустить t-rex.exe, проверьте настройки майнера!')
        if len(autotune_gmem_pool) != num_gpu:
            print('Настройки атотюна в config.ini некорректны, перезапускаю t-rex.exe ')
            start_trex_process(speed_fan=format_fan_speed(num_gpu, trex_fan), speed_gmem=format_gmem_default(num_gpu, trex_gmem), speed_gcore=format_gcore_default(num_gpu, trex_gcore), power_limit=power_limit(num_gpu, trex_power))
            time.sleep(40)
        else:
            print('Запускаю майнер')
            start_trex_process(speed_fan=format_fan_speed(num_gpu, trex_fan), speed_gmem=format_gmem(autotune_gmem_pool), speed_gcore=format_gcore(autotune_gcore_pool), power_limit=power_limit(num_gpu, trex_power))
            time.sleep(40)

# счетчик отклонений значений температур для каждой GPU
prev_autotune_gmem_pool = [] 
prev_autotune_gcore_pool = []
counter = 0
event_interval = 180
first_event = True
while True:
    counter += 1
    response = response_api(3)
    survey = response.json()
    prev_autotune_gmem_pool = autotune_gmem_pool.copy()
    prev_autotune_gcore_pool = autotune_gcore_pool.copy()
    for gpu in range(len(survey["gpus"])):
        log_gpus[gpu]["memory_temperature"] = survey["gpus"][gpu]["memory_temperature"]
        log_gpus[gpu]["temperature"] = survey["gpus"][gpu]["temperature"]
        # если жарко памяти, частоты постепенно сбрасываем
        if survey["gpus"][gpu]["memory_temperature"] >= temp_gmem_max:
            log_gpus[gpu]["max_mtemp_count"] += 1
            if log_gpus[gpu]["max_mtemp_count"] > 5:
                autotune_gmem_pool[survey["gpus"][gpu]["device_id"]] -= 100
                autotune_gcore_pool[survey["gpus"][gpu]["device_id"]] -= 50
                log_gpus[gpu]["max_mtemp_count"] = 0
        else:
            log_gpus[gpu]["max_mtemp_count"] = 0
        # если холодно, частоты постепенно поднимаем
        if survey["gpus"][gpu]["memory_temperature"] <= temp_gmem_max-temp_gmem_deviation:
            if autotune_gmem_pool[survey["gpus"][gpu]["device_id"]] < trex_gmem or autotune_gcore_pool[survey["gpus"][gpu]["device_id"]] < trex_gcore:
                log_gpus[gpu]["min_mtemp_count"] += 1
                if log_gpus[gpu]["min_mtemp_count"] > 5:
                    if autotune_gmem_pool[survey["gpus"][gpu]["device_id"]] < trex_gmem:
                        autotune_gmem_pool[survey["gpus"][gpu]["device_id"]] += 100
                    if autotune_gcore_pool[survey["gpus"][gpu]["device_id"]] < trex_gcore:
                        autotune_gcore_pool[survey["gpus"][gpu]["device_id"]] += 50
                    log_gpus[gpu]["min_mtemp_count"] = 0
            else:
                log_gpus[gpu]["min_mtemp_count"] = 0
        # если жарко ядру, частоты сбрасываем
        if survey["gpus"][gpu]["temperature"] >= temp_gcore_max:
            log_gpus[gpu]["max_ctemp_count"] += 1
            if log_gpus[gpu]["max_ctemp_count"] >= 5:
                autotune_gmem_pool[survey["gpus"][gpu]["device_id"]] -= 100
                autotune_gcore_pool[survey["gpus"][gpu]["device_id"]] -= 50
                log_gpus[gpu]["max_ctemp_count"] = 0
        else:
            log_gpus[gpu]["max_ctemp_count"] = 0
    # если частоты прошлого прохода отличаются от текущего -> кикаем процесс и запускаем с новыми значениями
    if prev_autotune_gmem_pool != autotune_gmem_pool or prev_autotune_gcore_pool != autotune_gcore_pool:
        trex_process = checker_trex_process()
        time.sleep(1)
        for process in trex_process[1:]:
            parts = process.split('","')
            pid = parts[1].strip('"')
            subprocess.call(f"taskkill /PID {pid} /F", shell=True)
        time.sleep(10) # время на убийство
        start_trex_process(speed_fan=format_fan_speed(num_gpu, trex_fan), speed_gmem=format_gmem(autotune_gmem_pool), speed_gcore=format_gcore(autotune_gcore_pool), power_limit=power_limit(num_gpu, trex_power))
        # записываем частоты в файл настроек
        conf = configparser.ConfigParser()
        conf.read('config.ini', encoding='utf-8')
        config['setting']['trex_gmem_pool'] = ','.join(map(str, autotune_gmem_pool))
        config['setting']['trex_gcore_pool'] = ','.join(map(str, autotune_gcore_pool))
        with open('config.ini', 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        time.sleep(40)
        tg_alert(
            f'Риг {rig_name} перезапущен с новыми настройками:'
            f'\nВремя: {time_samaran()}'
            f'\nCFX hashrate : {round(int(survey["hashrate"])/1000000, 2)} Mh'
            f'\nЧастоты MEM: {"/".join(map(str, autotune_gmem_pool))}'
            f'\nЧастоты CORE: {"/".join(map(str, autotune_gcore_pool))}'
            )
    if first_event or ((counter - 1) % event_interval == 0):
        message_tg = (
            stat_message
                (time_now=time_samaran(),
                trex_ver = survey["version"],
                hashrate = round(int(survey["hashrate"])/1000000, 2),
                data = log_gpus,
                autotune_gmem_pool = autotune_gmem_pool,
                autotune_gcore_pool = autotune_gcore_pool))
        tg_alert(message_tg)
        first_event = False
    time.sleep(monitoring_interval * 60)




"""log_gpus = []
    for gpu in json_data["gpus"]:
        try:
            memory_temp = int(gpu.get("memory_temperature", 0))
        except (ValueError, TypeError):
            memory_temp = 0
        try:
            core_temp = int(gpu.get("temperature", 0))
        except (ValueError, TypeError):
            core_temp = 0
        converted_gpu = {
            "device_id": gpu.get("device_id", 0),
            "name": gpu.get("name", ""),
            "memory_temperature": memory_temp,
            "temperature": core_temp,
            "memory_temp_deviation_count": 0,
            "core_temp_deviation_count": 0
        }
        log_gpus.append(converted_gpu)

    for i in log_gpus:
        if i["memory_temperature"] > temp_gmem_max or i["memory_temperature"] < temp_gmem_min:
            i["memory_temp_deviation_count"] += 1
        if i["temperature"] > temp_gcore_max or i["temperature"] < temp_gcore_min:
            i["core_temp_deviation_count"] += 1

    print(log_gpus)

else:
    print(f'Ошибка при выполнении запроса к api майнера. Код ошибки: {response.status_code}')

time.sleep(60)

alert = over_alert = 'Обнаружены следующие отклонения:'
        for i in json_data["gpus"]:
            if i["memory_temperature"] > temp_gmem_max:
                alert += f'\nТемп. памяти {i["name"]}-{int(i["device_id"])+1}: {i["memory_temperature"]}!'
            if i["temperature"] > temp_gcore_max:
                alert += f'\nТемп. ядра {i["name"]}-{int(i["device_id"])+1}: {i["temperature"]}!'
            if i["memory_temperature"] < temp_gmem_min:
                alert += f'\nТемп. памяти {i["name"]}-{int(i["device_id"])+1}: {i["memory_temperature"]}!'
            if i["temperature"] < temp_gcore_min:
                alert += f'\nТемп. ядра {i["name"]}-{int(i["device_id"])+1}: {i["temperature"]}!'
        if alert != over_alert:
            print(alert)"""


"""def kill_trex_process():
    try:
        cmd_processes = subprocess.check_output("tasklist /FI \"IMAGENAME eq t-rex.exe\" /FO CSV", shell=True).decode('cp866')
    except UnicodeDecodeError:
        try:
            cmd_processes = subprocess.check_output("tasklist /FI \"IMAGENAME eq t-rex.exe\" /FO CSV", shell=True).decode('cp437')
        except UnicodeDecodeError:
            print("Не удалось декодировать вывод команды tasklist.")
            return
    
    cmd_processes = cmd_processes.strip().split('\r\n')
    
    for process in cmd_processes[1:]:
        parts = process.split('","')
        pid = parts[1].strip('"')
        
        subprocess.call(f"taskkill /PID {pid} /F", shell=True)"""