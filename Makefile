# Release automation for claude-smart.
#
# Usage:
#   make bump VERSION=0.1.1          Update version in all 4 manifests
#   make release VERSION=0.1.1       Bump, commit, tag v0.1.1, publish, push
#   make publish                     Publish current version to npm + PyPI
#   make publish-npm                 npm publish only
#   make publish-pypi                uv build + uv publish only
#   make publish-dry                 Show what would ship without uploading
#
# Requires:
#   - npm (logged in, or NPM_TOKEN set)
#   - uv (UV_PUBLISH_TOKEN set for PyPI uploads)
#   - git (for the release flow)

.PHONY: help bump release publish publish-npm publish-pypi publish-dry \
        check-version check-clean

VERSION_FILES := package.json plugin/pyproject.toml \
                 plugin/.claude-plugin/plugin.json .claude-plugin/marketplace.json \
                 README.md

help:
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

check-version:
ifndef VERSION
	$(error VERSION is required, e.g. make bump VERSION=0.1.1)
endif
	@printf '%s' '$(VERSION)' | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$$' \
	  || { echo "error: VERSION '$(VERSION)' is not valid semver" >&2; exit 1; }

check-clean:
	@git diff --quiet && git diff --cached --quiet \
	  || { echo "error: working tree is dirty — commit or stash first" >&2; exit 1; }

bump: check-version ## Rewrite version in all 4 manifests
	@echo "→ bumping to $(VERSION)"
	@sed -i.bak -E 's/"version": "[^"]+"/"version": "$(VERSION)"/' \
	    package.json plugin/.claude-plugin/plugin.json .claude-plugin/marketplace.json
	@sed -i.bak -E 's/^version = "[^"]+"/version = "$(VERSION)"/' plugin/pyproject.toml
	@sed -i.bak -E 's|badge/version-[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?-green\.svg|badge/version-$(VERSION)-green.svg|' README.md
	@rm -f package.json.bak plugin/pyproject.toml.bak \
	       plugin/.claude-plugin/plugin.json.bak .claude-plugin/marketplace.json.bak \
	       README.md.bak
	@echo "→ resulting versions:"
	@grep -HE '("version"|^version)' $(VERSION_FILES)

publish-npm: ## Publish the current version to npm
	@echo "→ npm publish"
	npm publish --access public

publish-pypi: ## Build and publish the current version to PyPI
	@echo "→ uv build + uv publish"
	rm -rf plugin/dist/
	uv build --project plugin
	uv publish --project plugin plugin/dist/*

publish-dry: ## Show what would be published without uploading
	@echo "→ npm publish --dry-run"
	@npm publish --dry-run
	@echo ""
	@echo "→ uv build (dry: inspect plugin/dist/ manually)"
	rm -rf plugin/dist/
	uv build --project plugin
	@ls -la plugin/dist/

publish: publish-npm publish-pypi ## Publish to both npm and PyPI

release: check-version check-clean bump ## Bump + commit + tag + publish + push
	@echo "→ committing release v$(VERSION)"
	git add $(VERSION_FILES)
	git commit -m "Release v$(VERSION)"
	git tag -a v$(VERSION) -m "Release v$(VERSION)"
	@$(MAKE) publish
	@echo "→ pushing commit + tag"
	git push --follow-tags
	@echo "✓ released v$(VERSION)"
