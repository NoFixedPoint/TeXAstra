# Security

Open and compile only LaTeX projects you trust. The compiler supports Lua and
shell execution; a document can run code with your account's permissions. VS Code
Workspace Trust is required, but it is not a sandbox for trusted documents.

The browser interface binds to loopback and checks request origins. Do not expose
it through a public proxy. Generated files are kept in the user's cache.

For a suspected vulnerability, use GitHub's private vulnerability reporting for
this repository when available. Avoid posting exploit details or private source
documents in public issues.
