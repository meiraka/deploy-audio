.PHONY: all

all:
	ansible-playbook playbook.yml -i etc/ansible/hosts -u root --ask-pass
