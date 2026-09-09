# Local workspace layout

Open the parent folder in your editor so public code and private working material
are available together. The public repository is one child of that folder.

```text
rheo-stream-workspace/                 No .git directory here
  README.md                           Local orientation
  AGENTS.md                           Local working instructions
  .gitignore                          Ignore everything if Git is initialized here by mistake
  .dockerignore                       Exclude everything from an accidental parent build context
  workspace.paths.json                Local path map; no credentials
  rheo-stream/                        Public checkout; owns its own .git directory
  private/
    config/                           Private deployment settings and overrides
    documents/                        Source documents and working material
    agent-context/                    Personal instructions and context
    modules/                          Private extension source, explicitly registered when supported
  workspaces/                         Private databases, uploads, indexes, logs, and exports
  backups/                            Private backup destinations
```

The parent files and private directories are local to each installation. They are
not part of this repository. Use a fresh parent outside any existing Git repository;
clone or move the public checkout into it without copying any legacy Git history.
Create private directories with owner-only permissions, or equivalent service-account
permissions where collaboration is intended. This scaffold creates no real client
data, credentials, or running application.

From the parent, scope commands explicitly:

```sh
git -C rheo-stream status
python3 rheo-stream/scripts/check_repository.py
```

Use `rheo-stream/` as the context for future container builds and package publishing.
Do not publish the parent as an archive or initialize Git there. A parent ignore-all
file is only a guard against accidental staging; it can be bypassed. Private siblings
are excluded from the child repository by location, not by the child's `.gitignore`.

## Connecting the locations

Keep a local path map at the parent, with relative paths resolved against the file's
directory. For example:

```json
{
  "public_repository": "./rheo-stream",
  "private_configuration": "./private/config",
  "private_documents": "./private/documents",
  "private_agent_context": "./private/agent-context",
  "private_modules": "./private/modules",
  "runtime_workspaces": "./workspaces",
  "backups": "./backups"
}
```

This is an operator path map for the initial scaffold, not a versioned runtime API.
There is no automatic loader yet. When implemented, the host should accept an
explicit configuration location, validate and resolve its paths, then supply scoped
storage to modules. Do not make the source tree writable to store personalization.
Deployment policy must constrain path resolution, including traversal and symlink
escapes; an incoming event, model argument, or tenant setting cannot select a host
directory. Credentials belong in the selected secret store, not in this map.

The editor workspace root is a filesystem convenience. It is not an authenticated
Rheo Stream workspace and does not replace workspace or member authorization. A
single `workspaces/` data root may eventually contain several isolated application
workspaces managed by the host. Avoid deriving authorization from folder names.

Private modules can use the same contracts as public modules, but their presence
on disk must not cause automatic discovery or execution. Installation and explicit
registration still require the module lifecycle checks. Production packaging must
deliberately include authorized private extensions without publishing their source
or bundling their configuration and customer data into public artifacts.

## Working boundaries

- Keep private content out of public issues, PRs, fixtures, logs, and build assets.
  Editor visibility and local paths do not authorize disclosure to external tools.
- Do not add public-tree symlinks to the private siblings. Use explicit configuration
  references and trusted storage access instead.
- Keep test inputs synthetic. Test jobs must not discover and load a developer's
  local path map or live data automatically.
- Scope indexing, file watching, and tooling to the directories they need. The
  directory arrangement is not a sandbox for an agent or process with filesystem access.
- Backups remain private and need their own access, retention, and restore policy.
  Git does not back up these sibling directories, and this scaffold schedules no backups.

Installed applications may use an OS application-data directory instead. Hosted
deployments use operator-selected private databases and file/object storage; they
do not need this editor folder structure. All modes preserve the same
[private-data boundary](ideas/rheo-stream-idea.md#private-data-placement-in-each-deployment-mode).
