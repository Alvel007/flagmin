import subprocess

def kill_trex_process():
    try:
        processes = subprocess.check_output("tasklist /FI \"IMAGENAME eq t-rex.exe\" /FO CSV", shell=True).decode('cp866')
    except UnicodeDecodeError:
        print("Не удалось декодировать вывод команды tasklist.")
        return
    processes = processes.strip().split('\r\n')
    return processes

kill_trex_process()
for process in cmd_processes[1:]:
    parts = process.split('","')
    pid = parts[1].strip('"')
    
    subprocess.call(f"taskkill /PID {pid} /F", shell=True)

def check_trex_process():
    try:
        cmd_processes = subprocess.check_output("tasklist /FI \"IMAGENAME eq t-rex.exe\" /FO CSV", shell=True).decode('cp866')
    except UnicodeDecodeError:
        print("Не удалось декодировать вывод команды tasklist.")
        return
    
    cmd_processes = cmd_processes.strip().split('\r\n')
    
    if len(cmd_processes) > 1:
        print("Процесс t-rex.exe запущен.")
    else:
        print("Процесс t-rex.exe не запущен.")