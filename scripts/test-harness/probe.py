import argparse
import http.client
import datetime
import errno
import ipaddress
import json
import socket
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--target", required=True)
parser.add_argument("--web", action="store_true")
args = parser.parse_args()
target = str(ipaddress.ip_address(args.target))
results = []

for port in (8080, 8081):
    result = {
        "timeUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "destinationIp": target,
        "destinationPort": port,
        "expected": "Allow" if port == 8080 else "Deny",
    }
    try:
        if port == 8080:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({})
            )
            with opener.open(f"http://{target}:{port}/", timeout=15) as response:
                body = response.read().decode().strip()
                result["httpStatus"] = response.status
                result["passed"] = (
                    response.status == 200 and body == "vwan-harness-server"
                )
            result["observed"] = "HTTP response"
        else:
            with socket.create_connection((target, port), timeout=15):
                result["observed"] = "Connected unexpectedly"
                result["passed"] = False
    except (TimeoutError, socket.timeout) as error:
        result["observed"] = "Timed out"
        result["passed"] = port == 8081
        result["detail"] = str(error)
    except Exception as error:
        result["observed"] = "Error; requires investigation"
        result["passed"] = False
        result["detail"] = str(error)
    results.append(result)

if args.web:
    for host, expected in (
        ("www.example.com", "Allow"),
        ("www.microsoft.com", "Deny"),
    ):
        result = {
            "timeUtc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "fqdn": host,
            "url": f"http://{host}/",
            "destinationPort": 80,
            "expected": expected,
            "passed": False,
            "requiresFirewallLogVerification": True,
        }
        connection = None
        try:
            result["resolvedIps"] = sorted({
                entry[4][0] for entry in socket.getaddrinfo(
                    host, 80, type=socket.SOCK_STREAM
                )
            })
            connection = http.client.HTTPConnection(host, timeout=15)
            connection.request("GET", "/")
            response = connection.getresponse()
            result["httpStatus"] = response.status
            result["location"] = response.getheader("Location")
            result["observed"] = "HTTP response; redirect not followed"
            result["passed"] = (
                200 <= response.status < 400
                if expected == "Allow"
                else response.status == 403
            )
        except (TimeoutError, socket.timeout) as error:
            result["observed"] = "Timed out; firewall evidence required"
            result["passed"] = (
                expected == "Deny" and "resolvedIps" in result
            )
            result["detail"] = str(error)
        except Exception as error:
            result["observed"] = "Error; requires investigation"
            result["detail"] = str(error)
        finally:
            if connection:
                connection.close()
        results.append(result)

print(json.dumps(results, indent=2))
print("PROBES_PASS" if all(r["passed"] for r in results) else "PROBES_FAIL")
print("Firewall log verification is still required.")
