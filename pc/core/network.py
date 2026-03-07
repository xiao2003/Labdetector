import socket

def get_local_ip() -> str:
    """
    获取本机IP地址
    Returns:
        str: 本机IP地址
    """
    try:
        # 创建一个UDP socket，不实际发送数据
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 连接到一个公共DNS服务器（不会真正连接）
        s.connect(("8.8.8.8", 80))
        # 获取socket的IP地址
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # 备用方法
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"

def get_network_prefix() -> str:
    """
    获取网络前缀，如'192.168.1.'
    Returns:
        str: 网络前缀
    """
    local_ip = get_local_ip()
    # 假设是C类网络，前三个部分是网络前缀
    return '.'.join(local_ip.split('.')[:3]) + '.'