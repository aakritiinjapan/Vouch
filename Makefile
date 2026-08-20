# Convenience wrappers around demo.sh, for people who reach for make first.
.PHONY: demo reset test fixture clean

demo:            ## install, seed, and start both servers
	@./demo.sh

reset:           ## rebuild the database from the seed, then start
	@./demo.sh --reset

test:            ## run the backend test suite
	@./demo.sh --test

fixture:         ## regenerate the demo dataset from the real collector output
	@cd vouch/backend && python -m scripts.build_demo_fixture

clean:           ## remove the database, virtualenv, node_modules and logs
	@rm -rf vouch/backend/.venv vouch/backend/vouch.db vouch/frontend/node_modules \
	        .demo-api.log .demo-ui.log
	@echo "cleaned"
