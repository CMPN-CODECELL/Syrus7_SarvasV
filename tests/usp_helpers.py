def authenticate(client, platform, account_id="a", username="usp-user"):
    result = platform.auth.register(username, "secure-password", account_id)
    client.cookies.set("algoshield_session", result["token"])
    return result
