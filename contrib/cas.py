import httpx

params = (
    ("cas", "http://localhost:10000/auth/login"),
)

def getToken(self, user_id):
    headers = {
        "Authorization": f"Bearer test"
    }
    response = httpx.post(self.p.cas, json={"user_id": user_id}, headers=headers)
    data = response.json()
    if data["status"] == 1:
        raise Exception(data["data"])
    return data["data"]
