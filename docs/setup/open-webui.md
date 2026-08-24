
# Open WebUI Runtime Settings

Open WebUI configuration and user data are stored in the Compose-managed
`open_webui_data` volume.

This runtime data should not be version controlled.

## Local-model defaults

The Compose service keeps file context enabled but disables Open WebUI's
built-in autonomous tools by default. Small local models can otherwise render a
tool request such as `query_knowledge_files` as raw JSON instead of executing
it. Uploaded files still use Open WebUI's regular RAG context.

Background autocomplete, follow-up, and tag generation are also disabled so
they do not compete with chat inference. Chat title generation stays enabled,
with a plain-text prompt that forbids emoji; this prevents an emoji from
appearing beside the Open WebUI favicon in the browser tab.

Open WebUI persists administrator configuration. On an existing installation,
apply these once in the UI if a saved setting overrides the Compose defaults:

1. In **Admin Panel > Settings > Models**, disable **Builtin Tools**, enable
   **File Context**, and set **Function Calling** to **Legacy** for the bundled
   local model.
2. In **Admin Panel > Settings > Interface**, disable autocomplete, follow-up,
   and tag generation. Replace the title prompt with the value of
   `OPEN_WEBUI_TITLE_GENERATION_PROMPT_TEMPLATE` from `.env.example`.

Existing chat titles are stored data and are not renamed automatically. Rename
an old chat once if its title already starts with an emoji.
