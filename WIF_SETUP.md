# Keyless setup — Workload Identity Federation (no service-account key)

This replaces the `GOOGLE_SA_JSON` key. GitHub Actions authenticates to Google
with a short-lived OIDC token (no downloadable key), so your org's
`iam.disableServiceAccountKeyCreation` policy no longer blocks you.

> **Still required once:** a Workspace **super-admin** must authorise
> domain-wide delegation (Part D) so the bot can read the `cs@` inbox. WIF
> removes the *key*, not this one delegation step.

Easiest way to run the commands: open **Cloud Shell** (the `>_` icon, top-right
of the Google Cloud console). It runs as your account with `gcloud` preinstalled
— no local install. Paste the block below after filling in the four values.

---

## Part A — set your values

```bash
export PROJECT_ID="pivot-automation-xxxxx"     # your project ID (project picker → ID)
export REPO="YOUR_GH_USER/YOUR_REPO"           # e.g. minh44j/pivot-itinerary-cloud
export SA_NAME="pivot-bot"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud config set project "$PROJECT_ID"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
```

## Part B — enable APIs + let the SA sign for itself (keyless DWD)

```bash
gcloud services enable iamcredentials.googleapis.com gmail.googleapis.com drive.googleapis.com

# The SA mints its own delegated token via signBlob — grant it Token Creator on itself:
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## Part C — create the Workload Identity pool + GitHub provider

```bash
gcloud iam workload-identity-pools create github-pool \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'"

# Allow ONLY your repo to impersonate the service account:
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"

# Print the two values you'll paste into GitHub secrets:
echo "WORKLOAD_IDENTITY_PROVIDER = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo "SERVICE_ACCOUNT_EMAIL      = ${SA_EMAIL}"
```

## Part D — domain-wide delegation (Workspace super-admin, one time)

1. In Cloud Shell, get the SA's numeric client ID:
   ```bash
   gcloud iam service-accounts describe "$SA_EMAIL" --format='value(uniqueId)'
   ```
2. <https://admin.google.com> → **Security → Access and data control → API controls → Domain-wide delegation → Add new**.
3. **Client ID** = the number from step 1.
4. **OAuth scopes** (comma-separated):
   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/drive
   ```
5. **Authorize.**

## Part E — GitHub repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `WORKLOAD_IDENTITY_PROVIDER` | the `projects/.../providers/github-provider` string from Part C |
| `SERVICE_ACCOUNT_EMAIL` | `pivot-bot@<project>.iam.gserviceaccount.com` |
| `IMPERSONATE_USER` | `cs@pivot-travels.com` |
| `DRIVE_OUTPUT_FOLDER` | your Drive output-folder ID |
| `AKBAR_FOLDER_NAME` | `Pivot AI - Ticket PDFs` |
| `NOTIFY_TO` | *(optional)* override recipient; defaults to `cs@` |
| `SEARCH_WINDOW` | *(optional)* default `newer_than:2d` |

**Do NOT set `GOOGLE_SA_JSON`** — leaving it empty is what selects keyless mode.

## Part F — run it

Repo → **Actions → Pivot Itinerary Poll → Run workflow**. Check the **Authenticate
to Google (WIF)** step is green, then that a PDF lands in Drive and self-emails to
`cs@`. After that, the 15-min cron is automatic.
