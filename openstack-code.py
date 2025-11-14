import json
import requests
import urllib3
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

data = json.load(open('./url.json'))

class VirtualServerOpenstackService:
    def __init__(self):
        self.data = data
        self.user_domain_name = "default"
        self.project_domain_name = "default"
        self.vm_list = []
        self._token = None
        self._projects = None

    def get_current_time_truncated(self):
        now = datetime.now()
        now_truncated = now.replace(second=0, microsecond=0)
        return (now_truncated + timedelta(hours=0)).strftime('%Y-%m-%d %H:%M')

    def get_login(self):
        for key, value in self.data.items():
            if key == "credentials":
                continue
            cred_key = key
            user = self.data["credentials"][cred_key]["user"]
            password = self.data["credentials"][cred_key]["password"]
            for item in value:
                for url, ip_address in item.items():
                    print(f"Connecting to: {url}")
                    try:
                        self.get_token(user, password, ip_address)
                        self.all_projects(ip_address)
                        self.get_vms(ip_address, url, key)
                    except Exception as e:
                        print(f"Failed for {url}: {e}")

    def _headers(self):
        return {"X-Auth-Token": self._token, "OpenStack-API-Version": "compute 2.26"}

    def get_token(self, user, password, ip_address):
        payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {"user": {"name": user, "domain": {"name": self.user_domain_name}, "password": password}}
                },
                "scope": {"project": {"name": "admin", "domain": {"name": self.project_domain_name}}}
            }
        }

        for protocol in ["https", "http"]:
            try:
                resp = requests.post(
                    f"{protocol}://{ip_address}:5000/v3/auth/tokens",
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload),
                    verify=False
                )
                if resp.status_code == 201:
                    self._token = resp.headers.get("X-Subject-Token")
                    self._protocol = protocol
                    return self._token
            except Exception:
                continue

        raise Exception(f"{ip_address} HTTPS ve HTTP bağlantısı başarısız oldu!")

    def all_projects(self, ip_address):
        if self._projects:
            return self._projects
        protocols = [getattr(self, "_protocol", None)] if hasattr(self, "_protocol") else ["https", "http"]
        if protocols[0] is None:
            protocols = ["https", "http"]

        for protocol in protocols:
            try:
                url = f"{protocol}://{ip_address}:5000/v3/projects"
                resp = requests.get(url, headers=self._headers(), verify=False)
                if resp.status_code == 200:
                    self._projects = {p["id"]: p["name"] for p in resp.json().get("projects", [])}
                    self._protocol = protocol
                    return self._projects
            except Exception:
                continue
        raise Exception(f"{ip_address} projeler alınamadı!")

    def get_vms(self, ip_address, url, key):
        projects = self.all_projects(ip_address)
        protocols = [getattr(self, "_protocol", None)] if hasattr(self, "_protocol") else ["https", "http"]
        if protocols[0] is None:
            protocols = ["https", "http"]

        hypervisors, servers = [], []
        for protocol in protocols:
            try:
                resp_hv = requests.get(f"{protocol}://{ip_address}:8774/v2.1/os-hypervisors/detail", headers=self._headers(), verify=False)
                resp_sv = requests.get(f"{protocol}://{ip_address}:8774/v2.1/servers/detail?all_tenants=1", headers=self._headers(), verify=False)
                if resp_hv.status_code == 200 and resp_sv.status_code == 200:
                    hypervisors = resp_hv.json().get("hypervisors", [])
                    servers = resp_sv.json().get("servers", [])
                    self._protocol = protocol
                    break
            except Exception:
                continue

        if not hypervisors or not servers:
            raise Exception(f"{ip_address} hypervisor/server bilgisi alınamadı.")

        for hv in hypervisors:
            hv_short = hv.get("hypervisor_hostname", "").split('.')[0]
            for vm in servers:
                host_short = vm.get("OS-EXT-SRV-ATTR:host", "").split('.')[0]
                if host_short != hv_short:
                    continue

                project_name = projects.get(vm.get("tenant_id"), vm.get("tenant_id"))
                ip_add, vlan = "", ""
                for net_name, addr_list in vm.get("addresses", {}).items():
                    if addr_list:
                        ip_add = f"{addr_list[0].get('OS-EXT-IPS:type', '').capitalize()} IP: {addr_list[0].get('addr')}"
                        vlan = net_name
                        break

                guest_os = "Bilinmiyor"
                image = vm.get("image")
                image_id = image.get("id") if isinstance(image, dict) else image
                if image_id:
                    try:
                        image_url = f"{self._protocol}://{ip_address}:9292/v2/images/{image_id}"
                        resp = requests.get(image_url, headers=self._headers(), verify=False)
                        if resp.status_code == 200:
                            image_data = resp.json()
                            guest_os = (image_data.get("os_distro", "") + " " + image_data.get("os_version", "")).strip() or image_data.get("name", "") or "Bilinmiyor"
                    except Exception:
                        pass

                vm_info = {
                    "timestamp": self.get_current_time_truncated(),
                    "instance_name": vm.get("name", ""),
                    "id": vm.get("id", ""),
                    "project": project_name,
                    "status": vm.get("status", ""),
                    "ip_address": ip_add,
                    "vlan": vlan,
                    "guest_os": guest_os
                }
                self.vm_list.append(vm_info)

if __name__ == "__main__":
    service = VirtualServerOpenstackService()
    service.get_login()
    for vm in service.vm_list:
        print(vm)
