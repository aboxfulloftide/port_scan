"""
Shared TP-Link router authentication and API helpers.
Used by both the DHCP scraper and the traffic scraper.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger("worker.router_auth")


class RouterLoginError(Exception):
    def __init__(self, code: str, message: str, data: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


async def login_and_get_stok(page, router_url: str, username: str, password: str) -> Optional[str]:
    """
    Log into a TP-Link router using the JS widget encryption and return the stok token.
    The stok must be included in all subsequent API URL paths.
    """
    # Ensure we're on the login page
    try:
        if "/webpages/login.html" not in page.url:
            await page.goto(f"{router_url}/webpages/login.html", timeout=10000, wait_until="networkidle")
    except Exception:
        pass

    # Wait for TP-Link JS framework
    await page.wait_for_function("window.$ && $.su && $.su.url", timeout=8000)

    # Fill inputs, encrypt password, and read the encrypted value from .val()
    creds = await page.evaluate(
        """
        ({ username, password }) => {
            try { $("#login-username").textbox("setValue", username); } catch (e) { $("#login-username").val(username); }
            try { $("#login-password").password("setValue", password); } catch (e) { $("#login-password").val(password); }

            try { $("#login-password").password("doEncrypt"); } catch (e) {}

            let enc = null;
            try { enc = $("#login-password").val(); } catch (e) {}
            if (!enc) { try { enc = $("input[name='password']").val(); } catch (e) {} }

            return { enc, url: $.su.url("/login?form=login") };
        }
        """,
        {"username": username, "password": password},
    )

    login_url = creds.get("url") if isinstance(creds, dict) else "/login?form=login"
    enc = creds.get("enc") if isinstance(creds, dict) else None
    if not enc:
        enc = password  # last resort — will likely fail with error 700

    # Send login request
    login_resp = await page.evaluate(
        """
        async ({ loginUrl, username, enc }) => {
            const body = "data=" + encodeURIComponent(JSON.stringify({
                method: "login",
                params: { username, password: enc },
            }));
            const res = await fetch(loginUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body,
                credentials: "include",
            });
            return { ok: res.ok, status: res.status, text: await res.text() };
        }
        """,
        {"loginUrl": login_url, "username": username, "enc": enc},
    )

    if not isinstance(login_resp, dict) or not login_resp.get("text"):
        raise RouterLoginError("no_response", "No response from router login")

    try:
        data = json.loads(login_resp["text"])
    except json.JSONDecodeError:
        raise RouterLoginError("bad_json", f"Non-JSON login response: {login_resp['text'][:200]}")

    err_code = str(data.get("error_code", ""))
    if err_code and err_code != "0":
        result_data = data.get("result") or {}
        raise RouterLoginError(err_code, f"Router login error_code={err_code}", result_data if isinstance(result_data, dict) else {})

    # Extract stok from the login response
    stok = None
    result_data = data.get("result")
    if isinstance(result_data, dict):
        stok = result_data.get("stok")

    return stok


async def make_router_api_call(page, stok: str, router_url: str, path: str, form: str, quiet: bool = False) -> dict:
    """
    Make an authenticated POST call to the TP-Link router API.
    Returns the parsed JSON response data, or {} on failure.
    Set quiet=True to suppress warning logs (useful during endpoint discovery).
    """
    url = f"{router_url}/cgi-bin/luci/;stok={stok}/admin/{path}?form={form}"

    result = await page.evaluate("""
        async (url) => {
            const body = "data=" + encodeURIComponent(JSON.stringify({method: "get", params: {}}));
            const res = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body,
                credentials: "include",
            });
            const text = await res.text();
            return { ok: res.ok, status: res.status, text };
        }
    """, url)

    if not result or not result.get("ok"):
        if not quiet:
            logger.warning(f"Router API call {path}?form={form} failed: HTTP {result.get('status') if result else 'unknown'}")
        return {}

    data = json.loads(result.get("text") or "{}")
    err_code = str(data.get("error_code", ""))
    if err_code and err_code != "0":
        if not quiet:
            logger.warning(f"Router API {path}?form={form} returned error_code={err_code}")
        return {}

    return data
