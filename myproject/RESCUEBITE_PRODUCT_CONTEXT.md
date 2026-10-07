# RescueBite Product Context

**Purpose:** Factual product reference for a future retrieval-augmented help assistant. This document describes behavior visible in the current Django codebase. It is not a promise of future functionality.

## 1. Product Overview

RescueBite is a Django web application for coordinating surplus-food donations. It provides separate experiences for Food Donors, NGO/Receiver organizations, and Volunteers. Donors post food listings, NGOs can claim available listings, and Volunteers can view NGO-assigned deliveries and accept them for pickup/delivery. The home page describes the product's purpose as connecting surplus food with people who need it and reducing food waste.

The codebase supports these role-specific records and screens. It does not model food recipients as application accounts, record individual people served, or verify that a donation was ultimately consumed.

## 2. Product Goals

The home page states the goals of reducing food waste and addressing food insecurity by connecting donors, NGOs, and volunteers. Implemented outcomes include creating food listings, allowing NGOs to claim listings, and moving an NGO-assigned listing to an in-transit state when a Volunteer accepts it. The code does not establish measured impact beyond donation counts; some large homepage impact figures are explicitly labeled as placeholder targets.

## 3. Users and Roles

Each registered account uses Django's `User` model and has one role profile: `Donor`, `NGO`, or `Volunteer`. Login identifies the role from persisted profile relationships, and requires exactly one role profile.

### Food Donor (`Donor`)

- Registers an organization/contact profile and a location.
- Can access the Donor dashboard and create food listings associated with their profile.
- Can view their donation history, status, assigned NGO (when present), and the displayed distance to that NGO.
- No donor edit, cancel, or delete action is implemented in the current routes/views.
- Cannot use NGO or Volunteer role pages/actions.

### NGO / Receiver (`NGO`)

- Registers an organization/contact profile and a location.
- Can access the Receiver dashboard, browse open listings, and claim eligible listings.
- Claimed listings are associated with the NGO and appear in its claimed-food area.
- Cannot use Donor or Volunteer role pages/actions.
- A review dialog is displayed in the UI, but review submission is client-side only; no review endpoint or persistent review model is present.

### Volunteer (`Volunteer`)

- Registers a username, contact details, and a location.
- Can access the Volunteer dashboard and view food that is assigned to an NGO and has status `ASSIGNED`.
- Can accept an available assigned delivery, moving the food listing to `IN_TRANSIT`.
- The current data model does not associate the delivery with the Volunteer who accepted it. The dashboard therefore shows qualifying assigned food to each Volunteer, rather than a persisted Volunteer-specific assignment.
- There is no implemented Volunteer completion/received action.

## 4. Core Features

### Account registration

- **Purpose:** Create an account and one role profile.
- **Who:** Visitors using the home page.
- **How:** Choose the Volunteer, NGO Partner, or Food Donor form tab and submit it. The submit button selects the corresponding Django `ModelForm`. The view creates a Django auth account and the matching role profile within a database transaction, then logs the new account in.
- **Rules:** Email is normalized to lowercase. The view checks for an existing account username/email and existing role-profile email before creation; it also handles a concurrent uniqueness failure. Form errors are rendered on the submitted tab. Forms include a password field. Django's configured password validators are not explicitly run by this registration view.

### Login and logout

- **Purpose:** Authenticate accounts and send them to their role dashboard.
- **Who:** Registered users.
- **How:** Login accepts an email-like identifier and password. It searches Django users by username or email, authenticates candidates using Django authentication, determines the role from related profile records, and redirects to that dashboard.
- **Rules:** Accounts with no role profile or more than one role profile are not logged in through this flow. Existing accounts whose username differs from their profile email can log in by email. Logout clears the authenticated session and redirects to Login.

### Donor food listing

- **Purpose:** Record surplus food offered by a Donor.
- **Who:** Authenticated Donor accounts.
- **How:** The Donor dashboard form accepts a food name, quantity, shelf life in hours, optional description and image, and optional pickup latitude/longitude. The server associates the listing with the logged-in Donor and sets its initial status to `AVAILABLE`.
- **Rules:** Shelf life must be at least one hour. Pickup coordinates must either both be provided or both be blank. When omitted, the Donor's registered coordinates are used as the pickup location for map/distance display.
- **Limitations:** Quantity is free-form text. No food category, serving count, donor edit/cancel control, or automatic expiry job is implemented.

### NGO browsing and claiming

- **Purpose:** Let an NGO find and reserve a food listing.
- **Who:** Authenticated NGO accounts.
- **How:** The Receiver dashboard lists food with status `AVAILABLE` or `PENDING`. A claim action sends a CSRF-protected JSON POST with `food_id` to the claim endpoint. On success, the food status becomes `ASSIGNED` and `assigned_ngo` is set to the claiming NGO. The listing appears in that NGO's claimed-food area.
- **Rules:** Only an NGO profile may claim. Listings outside `AVAILABLE`/`PENDING` cannot be claimed. During a future `priority_expires_at` window, the listing can only be claimed by the NGO already referenced by `assigned_ngo`; otherwise the claim is rejected. A claim is an NGO assignment, not an exclusive assignment to a Volunteer.

### Volunteer delivery acceptance and map

- **Purpose:** Show NGO-assigned deliveries and allow a Volunteer to accept one for delivery.
- **Who:** Authenticated Volunteer accounts.
- **How:** The dashboard lists records with status `ASSIGNED` and a non-null NGO. The map displays donor/pickup-to-NGO routes using Leaflet, Leaflet Routing Machine, OpenStreetMap tiles, and OSRM. Accepting sends a CSRF-protected JSON POST with `food_id`; success changes status to `IN_TRANSIT` and removes the item from that dashboard view.
- **Rules and limitations:** Only a Volunteer profile may use the action, and only an `ASSIGNED` listing can be accepted. The Volunteer who accepts is not saved on the Food record. There is no subsequent pickup checkpoint, delivery-completion action, or endpoint that sets `RECEIVED`.
- **Coordinates:** A custom pickup coordinate pair is used when both coordinates exist. Otherwise the Donor's registered coordinates are used. The page can remain usable without map services, but route visualization depends on external map/routing services.

### Donation statistics and distance

- The home page shows database-derived donation totals and totals created since the start of the current month. Other large impact figures on the home page are labeled placeholder targets, not live figures.
- The Donor dashboard calculates a distance to the assigned NGO for display from pickup (or Donor) coordinates and NGO coordinates.
- A matching service provides great-circle distance and a helper that finds the nearest NGO. The current NGO claim view does not automatically call that nearest-NGO helper; NGOs manually claim listings visible to them.

### Help chat

- The home page includes a temporary help-chat panel. It sends a question to a CSRF-protected JSON POST endpoint and does not persist chat history or send account/donation records.
- The server-side help service uses the official OpenAI Python SDK and reads `OPENAI_API_KEY` from the server environment; its default model is `gpt-4o-mini` and can be overridden with `OPENAI_MODEL`.
- If the key is absent or the provider fails, the endpoint returns a friendly fallback. A real provider response requires a configured key and usable API access.

## 5. Application Workflows

### Visitor registration and role routing

```text
Home → select one role tab → submit that role's form
     → validate form and check duplicate identifiers
     → atomically create Django User + selected role profile
     → log in → redirect to that role's dashboard
```

Volunteer registration routes to `/volunteer/`; NGO registration routes to `/receiver/`; Donor registration routes to `/donor/`. Invalid or duplicate registrations render the home page with errors on the submitted form tab.

### Food donation, claim, and Volunteer acceptance

```text
Donor logs in → Donor dashboard → submit listing
     → Food created as AVAILABLE
NGO logs in → Receiver dashboard → claim listing
     → Food assigned_ngo set; status becomes ASSIGNED
Volunteer logs in → Volunteer dashboard → accept delivery
     → status becomes IN_TRANSIT
```

There is no implemented final transition to `RECEIVED`. The donor and assigned NGO dashboards display the listing's current status from the same Food record.

## 6. Pages and UI

| Page / route | Purpose and visible actions | Access |
|---|---|---|
| Home `/` | Product overview, how-it-works content, donation statistics, registration tabs, help chat; links to login and registration sections. | Public |
| Login `/login/` | Email and password sign-in. | Public |
| Donor dashboard `/donor/` | Donor's own donation history, status/NGO details, statistics, and new-donation form. | Authenticated Donor |
| Receiver dashboard `/receiver/` | Open listings, claim controls, and that NGO's claimed listings. | Authenticated NGO |
| Volunteer dashboard `/volunteer/` | NGO-assigned `ASSIGNED` tasks, route map, and accept-delivery controls. | Authenticated Volunteer |
| Admin `/admin/` | Django admin for registered application models, including Food status/list filters. | Django staff/superuser permissions |

### POST/action routes

| Route | Action and authorization |
|---|---|
| `/donor/create-food/` | Create a listing; requires login and Donor profile. |
| `/accept-donation/` | JSON claim action; POST-only, requires login and NGO profile. |
| `/volunteer/accept-delivery/` | JSON accept action; POST-only, requires login and Volunteer profile. |
| `/help/chat/` | JSON help question; POST-only and CSRF-protected; does not require login. |
| `/logout/` | Logs out the current session and redirects to Login. |

## 7. Food Domain

The central food-domain record is a `Food` donation/listing. It belongs to one Donor and may be associated with one NGO. Its quantity is descriptive text, shelf life is measured in hours, an image is optional, and a separate pickup location may be provided as a complete latitude/longitude pair. Creation and update timestamps are recorded.

`is_expired()` computes whether the listing's shelf-life interval has passed since creation. The current views do not automatically change the status based on that result or prevent a claim solely because the computed expiry time passed.

## 8. Data Model and Important Entities

### `User` (Django auth)

- Authentication identity, username/email, password hash, session login state, and standard Django auth relationships.
- RescueBite registration uses the normalized email as both username and email. Password authentication is handled by Django's user system.

### `Volunteer`

- Purpose: Volunteer role profile.
- Important fields: optional one-to-one `user` link (nullable for legacy profiles), unique `username`, unique `email`, `phone`, hashed legacy profile password field, latitude, longitude, and creation timestamp.
- The model has no relationship to a Food delivery and cannot record which Volunteer accepted a delivery.

### `NGO`

- Purpose: NGO/Receiver organization profile.
- Important fields: optional one-to-one `user` link (nullable for legacy profiles), organization name, contact, unique email, hashed profile password field, latitude, longitude, and creation timestamp.
- Related to claimed Food through `Food.assigned_ngo`.

### `Donor`

- Purpose: Donor organization profile.
- Important fields: required one-to-one `user`, organization name, contact, unique email, latitude, longitude, and creation timestamp.
- Related to its Food listings through `Food.donor` / `Donor.donated_foods`.

### `Food`

- Purpose: A Donor's surplus-food listing and its current workflow state.
- Important fields: donor, name, free-text `food_quantity`, optional description, positive shelf-life hours (default 24), optional image, status (default `AVAILABLE`), optional assigned NGO, timestamps, optional pickup coordinates, optional closest-distance value, and optional priority-window expiry timestamp.
- `Food.assigned_ngo` is nullable and uses `SET_NULL` on NGO deletion. `Food.donor` uses cascade deletion. The current model has no Volunteer assignment, claim-history, rating, or recipient entity.
- The `closest_distance_km` field exists in the schema; the Donor dashboard distance calculation is assigned in memory for display.

## 9. Statuses and Business Rules

| Stored status | Display meaning | Observed workflow support |
|---|---|---|
| `AVAILABLE` | Available for pickup | Initial state on donor creation; NGOs may browse and claim. |
| `PENDING` | Pickup requested | NGOs may browse/claim; no current view action was found that sets this state. |
| `ASSIGNED` | Assigned to NGO/Volunteer | Set when an NGO claims; shown to Volunteers when an NGO is linked. |
| `IN_TRANSIT` | Picked up by Volunteer / in transit | Set when a Volunteer accepts an assigned delivery. |
| `RECEIVED` | Successfully received | Choice exists, but no normal user action was found that sets it. |
| `EXPIRED` | Expired / not collected | Choice exists; expiry is computed by `is_expired()`, but no automatic status transition was found. |
| `CANCELLED` | Cancelled by donor | Choice exists, but no donor cancel action was found. |

Implemented state transitions:

```text
Food creation: AVAILABLE
NGO claim: AVAILABLE or PENDING → ASSIGNED (assigned_ngo set)
Volunteer accept: ASSIGNED → IN_TRANSIT
```

No transition to `RECEIVED`, `EXPIRED`, or `CANCELLED` was found in the current normal user workflows. Do not tell users that they can edit/cancel donations, complete delivery, or confirm receipt unless a future implementation adds those actions.

Other rules:

- Food shelf life entered on the donation form must be at least one hour.
- Custom pickup coordinates are optional but must be both present or both absent.
- Only authenticated users with the corresponding role profile may use a role dashboard or role action.
- An account with exactly one role profile is required for role-based login routing.
- Email is compared case-insensitively during registration duplicate checks and normalized to lowercase when registering.
- The claim endpoint checks status and the configured priority window. It does not run the nearest-NGO helper as an automatic assignment step.

## 10. Authentication and Permissions

- Django's built-in authentication system stores and verifies the primary account password hash. Role profile links determine routing and access; the login view does not infer the role from submitted fields or session labels.
- Registration is public and uses CSRF tokens in each form. Successful registration creates one user and the selected role profile inside a transaction, logs the user in, and redirects by role.
- Login is public. Incorrect credentials display a generic invalid email/password message. Missing or ambiguous role profiles are rejected.
- Logout clears the Django authentication session.
- Donor, Receiver, and Volunteer dashboards require authentication and then verify the correct related profile. Claim and delivery-accept actions are POST-only, check the appropriate role, and use Django CSRF middleware (the browser sends the CSRF token header for JSON requests).
- The chatbot is public but accepts only JSON POST requests, validates message content and length, and is CSRF-protected. Its provider key is read only on the server. No private user or donation details are added to the provider prompt.

## 11. Navigation Structure

```text
Home (/)
├── About / how it works / impact sections
├── Register: Volunteer | NGO Partner | Food Donor
├── May I Help You? chat panel
├── Login (/login/)
└── After login, exactly one profile selects a dashboard
    ├── Donor (/donor/)
    │   └── Create food listing (/donor/create-food/)
    ├── NGO / Receiver (/receiver/)
    │   └── Claim donation (/accept-donation/)
    └── Volunteer (/volunteer/)
        └── Accept delivery (/volunteer/accept-delivery/)

Authenticated navigation provides Logout (/logout/).
```

## 12. Important Terminology

| Term | Meaning in RescueBite |
|---|---|
| Donor | Registered organization/profile that posts surplus-food listings. |
| NGO / Receiver | Registered organization/profile that browses and claims available listings. |
| Volunteer | Registered role profile that can view NGO-assigned listings and accept delivery. |
| Food / donation / listing | A `Food` record posted by one Donor. |
| Claim | NGO action that associates the listing to that NGO and sets status to `ASSIGNED`. |
| Assigned NGO | The NGO related to a listing after claim. It is not a Volunteer assignment. |
| Pickup location | Optional coordinates on a Food record; if omitted, the Donor location is used for route/distance display. |
| Shelf life / expiry hours | Number of hours stored on the listing; `is_expired()` computes whether that interval elapsed. |
| In transit | `IN_TRANSIT` status set when a Volunteer accepts an `ASSIGNED` listing. |
| Priority window | Optional `priority_expires_at` timestamp used by the NGO listing visibility/claim checks. |

## 13. Frequently Asked Questions

### What is RescueBite?

RescueBite coordinates surplus-food listings between Donors, NGO/Receivers, and Volunteers. Donors post listings, NGOs claim them, and Volunteers can accept NGO-assigned deliveries.

### How do I register?

Open the home page, select the Volunteer, NGO Partner, or Food Donor tab, complete its form, and submit. A successful registration signs you in and opens the matching dashboard.

### How do I log in?

Use the Login page with the email address and password for your registered account. Login sends you to the dashboard associated with your single role profile.

### Which role should I choose?

Choose Food Donor if you represent an organization posting surplus food. Choose NGO Partner if your organization will browse and claim listings. Choose Volunteer if you want to view NGO-assigned delivery tasks and accept them. The application does not provide multi-role routing for a single account.

### How do I donate food?

Register or log in as a Food Donor, open the Donor dashboard, and submit the new-donation form with the food name, quantity, and shelf life. Description, image, and a complete custom pickup coordinate pair are optional. A successful listing starts as `AVAILABLE`.

### How does an NGO claim a listing?

Log in as an NGO/Receiver and browse the Receiver dashboard. Select Claim donation for a listing that is still available to claim. The system associates it with your NGO and sets it to `ASSIGNED`.

### What does a Volunteer do?

Log in as a Volunteer to view listings in `ASSIGNED` state with an assigned NGO. Accepting a listing changes it to `IN_TRANSIT`. The application does not currently provide an action to mark it delivered or received.

### Can I edit or cancel a donation?

No donor edit or cancellation action is implemented in the current application.

### Does the system automatically match each donation with the nearest NGO?

No automatic nearest-NGO assignment occurs in the current claim view. NGOs browse and claim listings; a nearest-NGO helper exists separately in the matching service.

### What happens when shelf life runs out?

The Food model can calculate whether the stored shelf-life duration elapsed. The current code does not automatically update the status to `EXPIRED` or document a user-facing expiry action.

### Can the help chat create an account or claim food for me?

No. It is informational only. It sends a question to the configured AI service and does not perform application actions.

## 14. Errors and Edge Cases

- **Missing/invalid registration fields:** The relevant Django form is rendered with validation errors and its tab remains selected. No account/profile is created unless the form is valid.
- **Duplicate registration email/username:** The form shows an email error and advises the visitor to log in. A transaction and integrity-error handling protect account/profile creation from partial registration.
- **Incorrect login:** A generic invalid email or password message is shown.
- **No role profile or multiple profiles:** Login does not authenticate/route the account into a RescueBite dashboard.
- **Wrong role for a dashboard:** The request is redirected to Login or Home according to that view's role guard.
- **Wrong role for NGO claim:** The JSON claim endpoint responds with HTTP 403.
- **Donation no longer claimable:** The claim endpoint rejects statuses other than `AVAILABLE`/`PENDING` with HTTP 400.
- **Priority-window restriction:** A nonmatching NGO is rejected while a listing is reserved by the priority rule (HTTP 403).
- **Volunteer accepts non-assigned food:** The action is rejected with HTTP 400. A non-Volunteer receives HTTP 403.
- **Invalid donor pickup pair or nonpositive shelf life:** The donation form displays field errors and does not create a Food record.
- **Unavailable map/routing library:** Volunteer route visualization falls back to a notice; the task list and acceptance action remain separate UI features.
- **Chatbot empty, malformed, or oversized message:** The endpoint returns a client error and does not call the provider. Provider/key/timeout failures return a friendly fallback without exposing credentials or exception details.
- **Unknown:** Exact user-facing behavior for every possible database, media-storage, or third-party map-service failure is not fully specified by current code.

## 15. Chatbot Knowledge Boundaries

### The chatbot can answer

- What RescueBite is and the purpose stated on the home page.
- What the Donor, NGO/Receiver, and Volunteer roles can do in the current implementation.
- Where registration and login are located and the role-routing behavior.
- How listings are created, claimed, and accepted into `IN_TRANSIT`.
- Implemented validation, visibility, status, and permission rules described in this document.

### The chatbot must not claim or assume

- That it can register users, log users in, create/edit/cancel donations, claim food, or change statuses.
- That delivery completion, a `RECEIVED` action, donor cancellation/editing, persistent NGO reviews, or a Volunteer-specific assignment is implemented.
- That nearest-NGO matching happens automatically during claim.
- That food is guaranteed safe, delivered, received, or consumed based solely on a listing/status.
- Private account information, credentials, database records, or information about a specific person's donations.
- Future features, undocumented rules, or that placeholder impact figures are live totals.

When this document does not contain the answer, the assistant should say the current project does not specify it and direct the user to the relevant application page or support contact only if such contact information is actually provided by the product.

## 16. Source Areas Inspected and Verification Notes

This context was derived from the current implementation in:

- `apps/main/models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, and `services/matching.py`.
- `apps/main/templates/main/` including the home, login, donor, receiver, volunteer, base, and shared partial templates.
- `apps/main/static/main/js/` and `apps/main/static/main/css/` for dashboard actions, navigation, maps, and chat UI.
- `config/settings.py`, `config/urls.py`, and the declared Python requirements.
- Existing tests under `tests/`.

No project README or existing product-context Markdown document was found at the project root during inspection. The implementation is the source of truth where page copy describes more than code supports. In particular, nearest-NGO automatic assignment, persisted reviews, Volunteer-to-delivery ownership, and final delivery completion are not implemented in the inspected workflows.

**Unknown / Not specified in current project:** actual food recipient identities and numbers; food-category taxonomy; food-safety verification procedures; delivery scheduling/time windows; donation editing/cancellation; Volunteer assignment ownership; proof-of-pickup/delivery; a normal user action that sets `RECEIVED`; persisted NGO reviews; automatic expiry handling; production deployment/provider key configuration; support contact details.
