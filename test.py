def format_gmem_default(num_gpu, trex_gmem):
    """Форматируем скорость вентилятора для старта майнера"""
    gmem_speeds = [trex_gmem - 300 for _ in range(num_gpu)]
    list_frequencies = [str(speed) for speed in gmem_speeds]
    return f"--mclock {','.join(list_frequencies)}"

print(format_gmem_default(num_gpu=2, trex_gmem=1500))