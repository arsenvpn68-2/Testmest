import base64
import json
import os
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse
import requests

CONFIG_PATH = "public/config.json"
TEST_URL = "https://www.gstatic.com/generate_204"

# کش برای جلوگیری از استعلام تکراری IPها
GEO_CACHE = {}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "brand_name": "𝔸𝕣𝕤𝕖𝕟VPℕ𓄂𓆃 ❻❽",
        "personal": [],
        "subs": [],
        "top_count": 20,
        "interval_minutes": 120,
        "last_run_timestamp": 0,
    }


def save_config(config_data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)


def get_flag_emoji(country_code):
    """تبدیل کد کشور ISO مانند US به ایموجی پرچم 🇺🇸"""
    if not country_code or len(country_code) != 2:
        return "🌐"
    country_code = country_code.upper()
    return chr(127397 + ord(country_code[0])) + chr(
        127397 + ord(country_code[1])
    )


def extract_host_from_node(node_link):
    """استخراج آدرس سرور (IP یا domain) از انواع پروتکل‌ها"""
    try:
        if node_link.startswith("vmess://"):
            b64_data = node_link.replace("vmess://", "")
            b64_data += "=" * (-len(b64_data) % 4)
            decoded = base64.b64decode(b64_data).decode("utf-8", errors="ignore")
            vmess_json = json.loads(decoded)
            return vmess_json.get("add", "")
        else:
            parsed = urlparse(node_link)
            return parsed.hostname or ""
    except Exception:
        return ""


def get_country_flag(node_link):
    """شناسایی موقعیت مکانی و دریافت پرچم کشور"""
    host = extract_host_from_node(node_link)
    if not host:
        return "🌐"

    if host in GEO_CACHE:
        return GEO_CACHE[host]

    try:
        ip = socket.gethostbyname(host)
        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        res = requests.get(url, timeout=3).json()
        if res.get("status") == "success":
            code = res.get("countryCode", "")
            flag = get_flag_emoji(code)
            GEO_CACHE[host] = flag
            return flag
    except Exception:
        pass

    GEO_CACHE[host] = "🌐"
    return "🌐"


def rename_node(node_link, new_name):
    """تغییر نام سرورهای عمومی بدون دست زدن به سرورهای شخصی"""
    try:
        if node_link.startswith("vmess://"):
            b64_data = node_link.replace("vmess://", "")
            b64_data += "=" * (-len(b64_data) % 4)
            decoded = base64.b64decode(b64_data).decode("utf-8", errors="ignore")
            vmess_json = json.loads(decoded)
            vmess_json["ps"] = new_name
            new_b64 = base64.b64encode(
                json.dumps(vmess_json, ensure_ascii=False).encode("utf-8")
            ).decode("utf-8")
            return "vmess://" + new_b64
        elif "#" in node_link:
            base_part = node_link.split("#")[0]
            return f"{base_part}#{quote(new_name)}"
        else:
            return f"{node_link}#{quote(new_name)}"
    except Exception:
        return node_link


def fetch_and_decode_subs(sub_urls):
    raw_nodes = []
    pattern = re.compile(
        r"^(vless|vmess|trojan|ss|ssr|tuic|hysteria2)://", re.IGNORECASE
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for url in sub_urls:
        url = url.strip()
        if not url:
            continue
        try:
            r = requests.get(url, headers=headers, timeout=12)
            content = r.text.strip()
            try:
                decoded = base64.b64decode(content).decode(
                    "utf-8", errors="ignore"
                )
                if any(
                    p in decoded
                    for p in ["vless://", "vmess://", "trojan://", "ss://"]
                ):
                    content = decoded
            except Exception:
                pass

            for line in content.splitlines():
                line = line.strip()
                if pattern.match(line):
                    raw_nodes.append(line)
        except Exception as e:
            print(f"Error fetching sub {url}: {e}")

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
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=8)
        return res.decode("utf-8")
    except Exception:
        return None


def test_single_node(node_info):
    index, node_link = node_info
    port = 10800 + (index % 1000)

    json_str = convert_node(node_link, "v2ray")
    if not json_str:
        return node_link, 0.1

    try:
        outbound_config = json.loads(json_str)
    except Exception:
        return node_link, 0.1

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
    time.sleep(1.2)

    proxies = {
        "http": f"socks5h://127.0.0.1:{port}",
        "https": f"socks5h://127.0.0.1:{port}",
    }
    score = 0.1

    try:
        t0 = time.time()
        res = requests.get(TEST_URL, proxies=proxies, timeout=5)
        if res.status_code in [200, 204]:
            latency = time.time() - t0
            score = max(1.0, 10.0 - latency)
    except Exception:
        pass
    finally:
        proc.terminate()
        proc.wait()
        if os.path.exists(config_filename):
            os.remove(config_filename)

    return node_link, score


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

    print("شروع فرایند پردازش...")
    personal_nodes = config.get("personal", [])
    sub_urls = config.get("subs", [])
    top_count = config.get("top_count", 20)
    brand_name = config.get("brand_name", "𝔸𝕣𝕤𝕖𝕟VPℕ𓄂𓆃 ❻❽")

    dynamic_nodes = fetch_and_decode_subs(sub_urls)
    print(f"تعداد {len(dynamic_nodes)} سرور عمومی دریافت شد.")

    if dynamic_nodes:
        indexed_nodes = list(enumerate(dynamic_nodes))
        tested_results = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(test_single_node, item) for item in indexed_nodes
            ]
            for future in as_completed(futures):
                link, score = future.result()
                if link:
                    tested_results.append((link, score))

        tested_results.sort(key=lambda x: x[1], reverse=True)
        best_dynamic = [x[0] for x in tested_results[:top_count]]
    else:
        best_dynamic = []

    # افزودن پرچم کشور به سرورهای عمومی برتر
    renamed_dynamic = []
    for idx, node in enumerate(best_dynamic, start=1):
        flag = get_country_flag(node)
        custom_title = f"{flag} {brand_name} - {idx:02d}"
        renamed_dynamic.append(rename_node(node, custom_title))

    # ترکیب: سرورهای شخصی (کاملاً دست‌نخورده) + سرورهای عمومی پرچمدار
    final_nodes = personal_nodes + renamed_dynamic
    generate_outputs(final_nodes)

    config["last_run_timestamp"] = current_time
    save_config(config)
    print(f"عملیات تمام شد. مجموع سرورها: {len(final_nodes)}")


if __name__ == "__main__":
    main()
