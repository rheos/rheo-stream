# Deployment templates

Reserved for generic local, self-hosted, and hosted deployment definitions once
the runtime and storage choices are made. There are no deployable services yet.

Templates contain placeholders and secret references only. Runtime workspace data
belongs in private databases and volumes, outside source and image build contexts.
The root `.dockerignore` is a source-only starting policy; every future image and
package needs its own content review. No deployment runs from the initial CI.
