import base64
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

CONFIG_PATH = "public/config.json"
TEST_URL = "https://speed.cloudflare.com/__down?bytes=5000000"


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "personal": [],
        "subs": [],
        "top_count": 20,
        "interval_minutes": 120,
        "last_run_timestamp": 0,
    }


def save_config(config_data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)


def fetch_and_decode_subs(sub_urls):
    raw_nodes = []
    pattern = re.compile(
        r"^(vless|vmess|trojan|ss|ssr|tuic|hysteria2)://", re.IGNORECASE
    )

    for url in sub_urls:
        if not url.strip():
            continue
        try:
            r = requests.get(
                url.strip(),
                headers={"User-Agent": "v2rayNG/1.8.5"},
                timeout=8,
            )
            content = r.text.strip()
            try:
                content = base64.b64decode(content).decode("utf-8", errors="ignore")
            except Exception:
                pass

            for line in content.splitlines():
                line = line.strip()
                if pattern.match(line):
                    raw_nodes.append(line)
        except Exception:
            pass

    return list(set(raw_nodes))


def convert_node(node_link, target_format):
    try:
        cmd = [
            "./subconverter/subconverter",
            "-g",
            "--generate-mode",
            "single",
            "--url",
            node_link,
            "--target",
            target_format,
        ]
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5)
        return res.decode("utf-8")
    except Exception:
        return None


def test_single_node(node_info):
    index, node_link = node_info
    port = 10800 + (index % 500)

    json_str = convert_node(node_link, "v2ray")
    if not json_str:
        return None, 0

    try:
        outbound_config = json.loads(json_str)
    except Exception:
        return None, 0

    config_filename = f"temp_xray_{port}.json"
    full_config = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "port": port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"udp": True},
        }],
        "outbounds": [outbound_config],
    }

    with open(config_filename, "w", encoding="utf-8") as f:
        json.dump(full_config, f)

    proc = subprocess.Popen(
        ["./xray", "run", "-c", config_filename],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)

    proxies = {
        "http": f"socks5h://127.0.0.1:{port}",
        "https": f"socks5h://127.0.0.1:{port}",
    }
    speed_mbps = 0

    try:
        t0 = time.time()
        res = requests.get(TEST_URL, proxies=proxies, timeout=3.5, stream=True)
        downloaded = 0
        for chunk in res.iter_content(chunk_size=32768):
            downloaded += len(chunk)
            if time.time() - t0 > 3.0:
                break
        dt = time.time() - t0
        if dt > 0 and downloaded > 0:
            speed_mbps = (downloaded * 8) / (dt * 1024 * 1024)
    except Exception:
        pass
    finally:
        proc.terminate()
        proc.wait()
        if os.path.exists(config_filename):
            os.remove(config_filename)

    return node_link, speed_mbps


def generate_outputs(final_nodes):
    os.makedirs("public", exist_ok=True)

    b64_out = base64.b64encode("\n".join(final_nodes).encode("utf-8")).decode(
        "utf-8"
    )
    with open("public/sub.txt", "w", encoding="utf-8") as f:
        f.write(b64_out)

    joined_nodes = "|".join(final_nodes)

    clash_yaml = convert_node(joined_nodes, "clash")
    if clash_yaml:
        with open("public/clash.yaml", "w", encoding="utf-8") as f:
            f.write(clash_yaml)

    singbox_json = convert_node(joined_nodes, "singbox")
    if singbox_json:
        with open("public/singbox.json", "w", encoding="utf-8") as f:
            f.write(singbox_json)


def main():
    config = load_config()
    current_time = int(time.time())
    interval_sec = config.get("interval_minutes", 120) * 60
    last_run = config.get("last_run_timestamp", 0)

    # بررسی زمان‌بندی هوشمند در اجراهای زمان‌بندی‌شده اکشن
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        if (current_time - last_run) < interval_sec:
            print("زمان تست فرا نرسیده است. خروج سریع.")
            return

    print("شروع فرایند پردازش و تست سرعت...")
    personal_nodes = config.get("personal", [])
    sub_urls = config.get("subs", [])
    top_count = config.get("top_count", 20)

    dynamic_nodes = fetch_and_decode_subs(sub_urls)
    print(f"تعداد {len(dynamic_nodes)} سرور عمومی برای تست استخراج شد.")

    indexed_nodes = list(enumerate(dynamic_nodes))
    tested_results = []

    # اجرای موازی تست‌ها با ۱۰ ورکر هم‌زمان
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(test_single_node, item) for item in indexed_nodes
        ]
        for future in as_completed(futures):
            link, speed = future.result()
            if link and speed > 0:
                tested_results.append((link, speed))

    tested_results.sort(key=lambda x: x[1], reverse=True)
    best_dynamic = [x[0] for x in tested_results[:top_count]]

    # ترکیب سرورها: شخصی‌ها دست‌نخورده در ابتدا + سرورهای عمومی برتر
    final_nodes = personal_nodes + best_dynamic
    generate_outputs(final_nodes)

    config["last_run_timestamp"] = current_time
    save_config(config)
    print("عملیات با موفقیت به پایان رسید.")


if __name__ == "__main__":
    main()
