def authenticate(
    client, platform, account_id="a", username="usp-user", *, operator=True
):
    result = platform.auth.register(username, "secure-password", account_id)
    # Integration operator fixture: trusted provisioning, never public promotion.
    if operator:
        platform.auth.provision_operator(username, granted=True)
    client.cookies.set("algoshield_session", result["token"])
    return result
