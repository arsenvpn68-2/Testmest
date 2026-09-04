import base64
import json
import os
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse
import requests

CONFIG_PATH = "public/config.json"
TEST_URL = "https://www.gstatic.com/generate_204"

GEO_CACHE = {}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "profiles" in data:
                    return data
        except Exception:
            pass
    return {
        "profiles": {
            "default": {
                "brand_name": "𝔸𝕣𝕤𝕖𝕟VPℕ𓄂𓆃 ❻❽",
                "total_gb": 50,
                "expire_days": 30,
                "personal": [],
                "subs": [],
                "top_count": 20,
            }
        }
    }


def get_flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "🌐"
    country_code = country_code.upper()
    return chr(127397 + ord(country_code[0])) + chr(
        127397 + ord(country_code[1])
    )


def extract_host_from_node(node_link):
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


def create_info_node(total_gb, expire_days):
    """ساخت سرور نمایش‌دهنده اطلاعات حساب در بالای نرم‌افزارها"""
    info_title = f"📊 Traffic: {total_gb} GB | ⏳ Remaining: {expire_days} Days"
    dummy_vless = f"vless://00000000-0000-0000-0000-000000000000@127.0.0.1:8080?type=tcp#{quote(info_title)}"
    return dummy_vless


def generate_outputs(profile_name, final_nodes, total_gb, expire_days):
    os.makedirs("public", exist_ok=True)
    suffix = "" if profile_name == "default" else f"_{profile_name}"

    # اضافه کردن سرور اطلاع‌رسانی به ابتدای لیست
    info_node = create_info_node(total_gb, expire_days)
    all_nodes_with_info = [info_node] + final_nodes

    b64_out = base64.b64encode(
        "\n".join(all_nodes_with_info).encode("utf-8")
    ).decode("utf-8")
    with open(f"public/sub{suffix}.txt", "w", encoding="utf-8") as f:
        f.write(b64_out)

    joined_nodes = "|".join(final_nodes)

    clash_yaml = convert_node(joined_nodes, "clash")
    if clash_yaml:
        with open(f"public/clash{suffix}.yaml", "w", encoding="utf-8") as f:
            f.write(clash_yaml)

    singbox_json = convert_node(joined_nodes, "singbox")
    if singbox_json:
        with open(f"public/singbox{suffix}.json", "w", encoding="utf-8") as f:
            f.write(singbox_json)


def cleanup_removed_profiles(active_profiles):
    """حذف فایل‌های مربوط به پروفایل‌هایی که پاک شده‌اند"""
    os.makedirs("public", exist_ok=True)
    for fname in os.listdir("public"):
        if (
            fname.startswith("sub_")
            or fname.startswith("clash_")
            or fname.startswith("singbox_")
        ):
            prof = (
                fname.split("_", 1)[1]
                .replace(".txt", "")
                .replace(".yaml", "")
                .replace(".json", "")
            )
            if prof not in active_profiles:
                try:
                    os.remove(os.path.join("public", fname))
                    print(f"فایل مربوط به پروفایل حذف‌شده پاک شد: {fname}")
                except Exception:
                    pass


def main():
    config = load_config()
    profiles = config.get("profiles", {})

    cleanup_removed_profiles(profiles.keys())

    print(f"شروع فرایند برای {len(profiles)} پروفایل...")

    for prof_name, prof_data in profiles.items():
        print(f"\n--- در حال پردازش پروفایل: {prof_name} ---")
        personal_nodes = prof_data.get("personal", [])
        sub_urls = prof_data.get("subs", [])
        top_count = prof_data.get("top_count", 20)
        brand_name = prof_data.get("brand_name", "𝔸𝕣𝕤𝕖𝕟VPℕ𓄂𓆃 ❻❽")
        total_gb = prof_data.get("total_gb", 50)
        expire_days = prof_data.get("expire_days", 30)

        dynamic_nodes = fetch_and_decode_subs(sub_urls)
        print(f"تعداد {len(dynamic_nodes)} سرور عمومی دریافت شد.")

        if dynamic_nodes:
            indexed_nodes = list(enumerate(dynamic_nodes))
            tested_results = []

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(test_single_node, item)
                    for item in indexed_nodes
                ]
                for future in as_completed(futures):
                    link, score = future.result()
                    if link:
                        tested_results.append((link, score))

            tested_results.sort(key=lambda x: x[1], reverse=True)
            best_dynamic = [x[0] for x in tested_results[:top_count]]
        else:
            best_dynamic = []

        renamed_dynamic = []
        for idx, node in enumerate(best_dynamic, start=1):
            flag = get_country_flag(node)
            custom_title = f"{flag} {brand_name} - {idx:02d}"
            renamed_dynamic.append(rename_node(node, custom_title))

        final_nodes = personal_nodes + renamed_dynamic
        generate_outputs(prof_name, final_nodes, total_gb, expire_days)

    print("\nعملیات ساخت کلیه پروفایل‌ها با موفقیت تمام شد.")


if __name__ == "__main__":
    main()
