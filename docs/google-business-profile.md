# Google Business Profile and reviews — Induduzo Funeral Home

## Existing Google entry

Google Maps already shows [Induduzo Funeral Home in Edendale](https://www.google.com/maps/place/Induduzo+Funeral+Home/@-29.6482444,30.3186257,17z/data=!3m1!4b1!4m6!3m5!1s0x1ef6a2e73a0f7019:0x2cad98db42535559!8m2!3d-29.6482444!4d30.3186257!16s%2Fg%2F11jwswk2nl). As checked on 15 September 2026, it has one public review, a 5.0 rating, a `Funeral home` category, and a `Claim this business` link. It lacks a public phone number and website and shows only `Edendale, Pietermaritzburg, 3217` for its address.

This is the entry to claim and verify. [Google's profile guidelines](https://support.google.com/business/answer/3038177?hl=en) call for one profile per business. Do not create a duplicate for the same Edendale office; that would split the review history and can cause Maps/Search problems. A different physical branch would need its own separately verified details.

On 15 September 2026, suggestions were submitted through Google Maps for the official website, primary phone and confirmed address. Google acknowledged all three and said it would email when reviewed. They are **pending suggestions**, not verified profile edits.

The owner setup wizard explicitly matched the existing `Induduzo Funeral Home, Edendale, Pietermaritzburg` profile, and that match was selected. The account holder entered the six-digit verification code sent to the primary phone. Google now shows **You manage this Business Profile** but says verification is still processing and may take up to five days.

## Profile details ready to enter after claim

| Field | Value |
|---|---|
| Real-world business name | Induduzo Funeral Home |
| Primary category | Funeral home (already shown) |
| Business address | Edendale Main Road, Kwadaya, Pietermaritzburg, KwaZulu-Natal 3201, South Africa |
| Website | https://induduzo.co.za/ |
| Primary phone | +27 79 751 0648 |
| Additional phone if supported | +27 82 954 9241 |
| WhatsApp chat link if the regional option is offered | https://wa.me/27797510648 |
| Service areas to verify with office | Pietermaritzburg and the KwaZulu-Natal Midlands |
| Hours | Daily 07:00–17:00, South African time, entered in the profile |

Suggested business description (no URLs, prices or promotions):

> Induduzo Funeral Home is a family-run funeral home serving families in Pietermaritzburg and the KwaZulu-Natal Midlands. We provide dignified funeral arrangements, funeral plans, repatriations, pre-planning, exhumations, caskets and related support. Our team offers compassionate guidance in English and isiZulu and is available by phone when families need help.

The street address and postal code `3201` were confirmed by the user. The owner supplied a map reference at the corner of Selby Msimang Road and Hh100, and the profile editor has been set to show a customer-facing address with the pin in that mapped area. Google still displays an “Address can't be found” warning for the free-text address, so confirm the pin and the final published address after verification. Add authentic exterior signage, office and service photos after verification. If customers cannot visit the office, configure a service-area business and hide the address instead.

The managed profile currently contains the primary phone `079 751 0648`, additional phone `082 954 9241`, website `https://induduzo.co.za/`, WhatsApp chat `https://wa.me/27797510648`, the prepared description, funeral-home services, and daily 07:00–17:00 hours. Google is still processing verification, so these edits may remain pending until the review completes.

The direct [Google review form](https://search.google.com/local/writereview?placeid=ChIJGXAPOuei9h4RWVVTQtuYrSw) was opened and confirmed to resolve to this Edendale business. After verification, use **Read reviews → Get more reviews** to copy Google's current owner-provided review link or QR code, then use that in the member follow-up flow. Ask only families with a genuine experience and do not offer incentives. See [Google's review-link instructions](https://support.google.com/business/answer/16816815?hl=en-GB) and [review policy](https://support.google.com/business/answer/3474122?hl=en).

## Review API for the staff portal

The full review feed is Google's [Business Profile Reviews API](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/list):

```text
GET https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews
```

It returns paginated `reviews`, `averageRating`, `totalReviewCount` and `nextPageToken`; a page can contain up to 50 reviews. The location must be **verified**. OAuth requires the `https://www.googleapis.com/auth/business.manage` scope, the Google account must manage the profile, and the Google Cloud project must be approved for Business Profile API access. [Google's API FAQ](https://developers.google.com/my-business/content/faq) says access must be requested and reviewed; it does not automatically grant access to any public listing. Keep the OAuth credentials and refresh token in `backend/` only.

[The existing review-loop brief](feature-1-review-loop.md) already sets the correct architecture: a backend job pulls Google data into Postgres, and the staff portal reads a protected backend endpoint. The portal should show rating, review count, recent reviews and reply status from the backend; no `VITE_*` Google token or direct browser call. Paginate and upsert reviews by Google's review ID, and record the last successful sync so a Google outage does not erase portal data. Keep reviewer names and review text out of logs. Owner replies can later use the same API's `updateReply` endpoint, with an explicit staff action and audit trail.

If Business Profile API approval is unavailable, [Places API (New) Place Details](https://developers.google.com/maps/documentation/places/web-service/place-details) can expose public average rating, review count and up to **five** reviews for a Place ID. That is a limited, billed fallback and cannot support a full historical review inbox or owner replies. Its API key also belongs in `backend/`, not the portal build.

## Site discovery

The website now includes a linked Google Maps address, a Google review link, `LocalBusiness` JSON-LD, `sitemap.xml`, and `llms.txt`. The latter is a short public-site guide for tools that choose to read it. [Google's AI Search guidance](https://developers.google.com/search/docs/appearance/ai-features) explicitly says special AI text files are not required for AI Overviews or AI Mode; it recommends crawlable text, accurate Business Profile information and Search Console. Add the site to Search Console, submit the sitemap and check indexing after the next public-site deployment.
