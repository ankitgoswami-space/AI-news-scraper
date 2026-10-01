import requests
from bs4 import BeautifulSoup


url = "https://analyticsindiamag.com/"

response = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    }
)

print("Status code:", response.status_code)
print("Page length:", len(response.text))


soup = BeautifulSoup(response.text, "html.parser")

print("Page title:", soup.title.get_text(strip=True))


body = soup.body

print("Body found:", body is not None)

print("First 5000 characters of body:")
print(body.prettify()[:5000])


scripts = soup.find_all("script")

print("Scripts found:", len(scripts))

for script in scripts:
    src = script.get("src")

    if src:
        print(src)


script_url = "https://analyticsindiamag.com/assets/index-Bpe3UPrl.js"

js_response = requests.get(
    script_url,
    headers={
        "User-Agent": "Mozilla/5.0"
    }
)

print("JS status code:", js_response.status_code)
print("JS file length:", len(js_response.text))


js_text = js_response.text

keywords = [
    "api",
    "fetch(",
    "axios",
    "/api/",
]

for keyword in keywords:
    count = js_text.lower().count(keyword.lower())

    print(f"{keyword}: {count}")

search_term = "fetch("
start = 0
count = 0

while True:
    position = js_text.lower().find(search_term.lower(), start)

    if position == -1:
        break

    count += 1

    print("\nFETCH FOUND:", count)
    print("Position:", position)
    print(js_text[position - 300:position + 700])

    start = position + len(search_term)

search_term = "zdpdvwhvukelzzbzbjvh"

position = js_text.find(search_term)

print("\nSupabase project found at:", position)

print(js_text[position - 1000:position + 3000])