import os
import time
from datetime import datetime

import pandas as pd
import requests

# Configuration
token = os.getenv("SKYPORTAL_API_TOKEN")
if not token:
    raise ValueError("SKYPORTAL_API_TOKEN environment variable is not set")
base_url = "https://skyportal-icare.ijclab.in2p3.fr/api"
headers = {"Authorization": f"token {token}"}
max_retries = 3

# List of source names to fetch data for
source_names = ["2025aji", "GCN-260511_061333"]

if not source_names:
    raise ValueError("source_names list is empty — add source IDs to process")


def api_get(url, params=None):
    for _ in range(max_retries):
        r = requests.get(url, headers=headers, params=params)
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} on {url}")
            time.sleep(2)
            continue
        data = r.json()
        if data.get("status") == "success":
            return data["data"]
        print(f"  API error: {data.get('message')}; waiting 5s...")
        time.sleep(5)
    return None


all_sources = []
all_comments = []
all_photometry = []

for name in source_names:
    print(f"\nProcessing source: {name}")

    source = api_get(f"{base_url}/sources/{name}")
    if source is None:
        print(f"  Could not retrieve source {name}, skipping.")
        continue

    ra = source.get("ra")
    dec = source.get("dec")
    redshift = source.get("redshift")
    t0 = source.get("t0")
    tns_name = source.get("tns_name")

    all_sources.append(
        {
            "source_id": name,
            "ra": ra,
            "dec": dec,
            "redshift": redshift,
            "t0": t0,
            "tns_name": tns_name,
        }
    )
    print(f"  Localization: RA={ra}, Dec={dec}")

    comments = api_get(f"{base_url}/sources/{name}/comments")
    if comments is not None:
        comment_list = (
            comments if isinstance(comments, list) else comments.get("comments", [])
        )
        for c in comment_list:
            all_comments.append(
                {
                    "source_id": name,
                    "comment_id": c.get("id"),
                    "author_id": c.get("author_id"),  # author relationship is lazy-loaded; only author_id is in to_dict()
                    "created_at": c.get("created_at"),
                    "text": c.get("text"),
                }
            )
        print(f"  Retrieved {len(comment_list)} comments")
    else:
        print("  Could not retrieve comments")

    photometry = api_get(
        f"{base_url}/sources/{name}/photometry",
        params={"format": "flux"},
    )
    if photometry is not None:
        phot_list = photometry if isinstance(photometry, list) else []
        for p in phot_list:
            all_photometry.append(
                {
                    "source_id": name,
                    "mjd": p.get("mjd"),
                    "filter": p.get("filter"),
                    "flux": p.get("flux"),
                    "fluxerr": p.get("fluxerr"),
                    "instrument_name": p.get("instrument_name"),
                    "origin": p.get("origin"),
                }
            )
        print(f"  Retrieved {len(phot_list)} photometry points")
    else:
        print("  Could not retrieve photometry")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

df_sources = pd.DataFrame(all_sources)
sources_file = f"sources_{timestamp}.csv"
df_sources.to_csv(sources_file, index=False)
print(f"\nSaved {len(all_sources)} sources to {sources_file}")

df_comments = pd.DataFrame(all_comments)
comments_file = f"comments_{timestamp}.csv"
df_comments.to_csv(comments_file, index=False)
print(f"Saved {len(all_comments)} comments to {comments_file}")

df_phot = pd.DataFrame(all_photometry)
phot_file = f"lightcurves_{timestamp}.csv"
df_phot.to_csv(phot_file, index=False)
print(f"Saved {len(all_photometry)} photometry points to {phot_file}")
