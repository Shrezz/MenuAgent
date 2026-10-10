# Household persistence

The app persists household members, preferences and manual inventory in PostgreSQL. Structured recipes and source-food cache entries now persist too. Weekly menus and history remain preview data until their own milestones. New database households start empty.

## Local database

After installing requirements.txt:

```sh
python -m database.local setup
python -m streamlit run streamlit_app.py
```

Automatic setup prefers Docker. Select --backend docker or --backend native if needed. Docker uses the official postgres:17 image, a project-specific container/volume and a port published only on 127.0.0.1, default 55432. Native setup requires initdb, pg_ctl and PostgreSQL on PATH; it uses a private Unix socket and peer authentication. Both support start, stop and status through the same module. Stopping retains data; repeat setup retains the household and records.

Private .local/runtime.json selects the app connection and household. Docker's separate .local/postgres-admin.json stores bootstrap credentials. Directory/file permissions are 0700/0600. These files, database files and all .env/secret files are ignored by Git. Never share private runtime files or include them in artifact archives.

Docker is verified in this workspace. Native PostgreSQL startup is blocked by shared-memory restrictions, so native development support is not claimed as tested here.

## Backend configuration

| Variable | Purpose |
| --- | --- |
| MENUAGENT_MODE | auto (default), preview, or postgres. Explicit preview ignores saved database settings. |
| MENUAGENT_DATABASE_URL | App connection from backend environment/secret storage; overrides local configuration. |
| MENUAGENT_HOUSEHOLD_ID | Provisioned household UUID selected by the server, never browser input. |
| MENUAGENT_ACCESS_MODE | local for this machine's editor; oidc for a configured identity provider. |
| MENUAGENT_LOCAL_EDITOR_SUBJECT | Trusted local editor identity; default local-editor. Requires loopback binding. |
| MENUAGENT_RUNTIME_FILE | Optional alternative private runtime-config path. |
| MENUAGENT_ADMIN_DATABASE_URL | Administrative migration/provisioning connection; never the application connection. |

Connections, household IDs and editor identities never come from UI forms. Configured database failures display an error; the app does not substitute a sample household. The Streamlit configuration binds to 127.0.0.1.

## Migrations and editor access

For another deployment, provision an application LOGIN role without superuser/RLS bypass privileges and a separate admin connection. Supply connections through backend environment/secret storage, then run:

```sh
python -m database.manage migrate --app-role menuagent_app
python -m database.manage bootstrap --name 'My household' --editor-subject local-editor
```

Bootstrap prints the new household UUID for server configuration. Migrations use transactions, advisory locking and checksums. Do not edit an applied migration; add a numbered SQL migration. Migration 002 adds nullable cooking-effort/meal-prep choices and recurring busy days. Historical minute budgets remain stored but are no longer read or enforced; no effort preference is guessed from them. Repeat provisioning does not reset records.

Migration 003 adds recipe_versions and food_sources, with the same household/editor row policies. Recipes are insert-only immutable revisions for the app role; source cache updates do not rewrite saved recipe snapshots.

editor_access is administrator-provisioned. The application can read its editor's memberships but cannot grant access. Members and stock have household-scoped keys; queries filter by household and PostgreSQL enforces household/editor row policies. Transaction-local settings clear when connections close. Runtime uses short-lived connections and rejects superuser/RLS bypass roles.

Local mode is the verified MVP access path. For remote hosting, configure Streamlit authentication through deployment secrets, choose MENUAGENT_ACCESS_MODE=oidc and provision an editor subject made from the provider's iss and sub claims, separated by |. Claims determine editor identity; there is no household picker or self-registration. A real provider login still needs deployment verification. See [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication).

## Saves and concurrent edits

Successful writes increment the household version. Browser sessions retain their loaded version. Stale saves are rejected with instructions to use **Reload saved household**. Reload clears profile/preference/stock widget values before refreshing the form.

Stock replacements are one transaction: deletion, insertion and version advancement either all commit or roll back. Blank quantities remain unknown. Whitespace and case normalization distinguish stock within location/unit; canonical food matching arrives in milestone 2.

## Verification

```sh
python -m database.test
```

The runner reads private local credentials into process memory, creates a unique test database, runs the suite and drops the test database. Credentials never appear in command arguments. For another environment, set MENUAGENT_TEST_ADMIN_DATABASE_URL and MENUAGENT_TEST_DATABASE_URL, then use python -m unittest discover -s tests. The test admin role must create/drop test databases and provision schemas; the app role must authenticate to generated database names.

Tests cover real transactions, cross-household access, raw SQL RLS checks, stale versions, rollback, child defaults, invalid inputs and Streamlit saves across new sessions. Live remote OIDC login, backup/restore and production deployment remain outside this milestone.
