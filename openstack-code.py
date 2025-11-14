import json
import requests
from datetime import datetime, timedelta

# JSON dosyasını yükle
data = json.load(open('./url.json'))

class OpenstackService:
    def __init__(self):
        self.data = data
        self.user_domain_name = "default"
        self.project_domain_name = "default"
        self._token = None
        self._protocol = None
        self._projects = None

    def get_current_time_truncated(self):
        now = datetime.now().replace(second=0, microsecond=0)
        return now.strftime('%Y-%m-%d %H:%M')

    def get_login(self):
        for key, value in self.data.items():
            if key == "credentials":
                continue
            cred_key = key
            user = self.data["credentials"][cred_key]["user"]
            password = self.data["credentials"][cred_key]["password"]
            for item in value:
                for url, ip_address in item.items():
                    print(f"Connecting: {url}")
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
                "identity": {"methods": ["password"], "password": {"user": {"name": user, "domain": {"name": self.user_domain_name}, "password": password}}},
                "scope": {"project": {"name": "admin", "domain": {"name": self.project_domain_name}}}
            }
        }

        for protocol in ["https", "http"]:
            try:
                resp = requests.post(f"{protocol}://{ip_address}:5000/v3/auth/tokens",
                                     headers={"Content-Type": "application/json"}, 
                                     data=json.dumps(payload), verify=False)
                if resp.status_code == 201:
                    self._token = resp.headers.get("X-Subject-Token")
                    self._protocol = protocol
                    return
            except Exception:
                continue
        raise Exception(f"{ip_address} connection failed!")

    def all_projects(self, ip_address):
        if self._projects:
            return self._projects

        resp = requests.get(f"{self._protocol}://{ip_address}:5000/v3/projects", headers=self._headers(), verify=False)
        if resp.status_code == 200:
            self._projects = {p["id"]: p["name"] for p in resp.json().get("projects", [])}
            return self._projects
        raise Exception("Failed to fetch projects")

    def get_vms(self, ip_address, url, key):
        projects = self.all_projects(ip_address)
        resp_hv = requests.get(f"{self._protocol}://{ip_address}:8774/v2.1/os-hypervisors/detail", headers=self._headers(), verify=False)
        resp_sv = requests.get(f"{self._protocol}://{ip_address}:8774/v2.1/servers/detail?all_tenants=1", headers=self._headers(), verify=False)

        hypervisors = resp_hv.json().get("hypervisors", []) if resp_hv.status_code == 200 else []
        servers = resp_sv.json().get("servers", []) if resp_sv.status_code == 200 else []

        if not hypervisors or not servers:
            raise Exception(f"No hypervisors or servers found for {ip_address}")

        domain = key.split("_")[-1] if "_" in key else ""
        environment = key.split("_")[0] if "_" in key else ""

        for hv in hypervisors:
            hv_short = hv.get("hypervisor_hostname", "").split('.')[0]
            host_vms = [vm for vm in servers if vm.get("OS-EXT-SRV-ATTR:host", "").split('.')[0] == hv_short]

            for vm in host_vms:
                project_name = projects.get(vm.get("tenant_id"), vm.get("tenant_id"))
                flavor = vm.get("flavor", {})
                ip_add, vlan = "", ""
                for net_name, addr_list in vm.get("addresses", {}).items():
                    if addr_list:
                        ip_add = addr_list[0].get("addr", "")
                        vlan = net_name
                        break

                vm_tuple = (
                    self.get_current_time_truncated(),
                    url,
                    vm.get("OS-EXT-AZ:availability_zone", ""),
                    vm.get("name", ""),
                    vm.get("id", ""),
                    vlan,
                    vm.get("status", ""),
                    ip_add,
                    float(flavor.get("vcpus", 0)),
                    float(round(flavor.get("ram", 0)/1024, 1)),
                    float(flavor.get("disk", 0)),
                    vm.get("image", ""),
                    domain,
                    environment,
                    self.user_domain_name,
                    flavor.get("name", ""),
                    project_name,
                    vm.get("created", ""),
                    ",".join(vm.get("tags", [])) if isinstance(vm.get("tags"), list) else "",
                )
                print(vm_tuple)


if __name__ == "__main__":
    service = OpenstackService()
    service.get_login()
