DOCKERHUB ?= "swr.cn-north-4.myhuaweicloud.com/weizhanjun"
PROJECTNAME ?= "aiga-chat"
DOCKERFILE_DIR ?= "./"
TAG ?= $(shell date +%Y%m%d%H%M%S)

.DEFAULT_GOAL=help
.PHONY=help
help:
	@awk -F ':|##' '/^[^\t].+?:.*?##/ {\
	printf "\033[36m%-30s\033[0m %s\n", $$1, $$NF \
	}' $(MAKEFILE_LIST)


docker-build: ## build docker image, need tags
	docker build -t $(DOCKERHUB)/$(PROJECTNAME):$(TAG) -f $(DOCKERFILE_DIR)/Dockerfile .


docker-buildx: ## build multi platform images and push it, need tags
	docker buildx build --platform linux/arm64,linux/amd64 --push \
		-t $(DOCKERHUB)$(PROJECTNAME):$(TAG) -f $(DOCKERFILE_DIR)/Dockerfile .

docker-build-enima: ## build enigma docker image, need tags
    docker build -t $(DOCKERHUB)/chat-enigma:$(TAG) -f enigma/Dockerfile ./enigma

docker-push-enima: ## push enigma docker image, need tags
    docker push $(DOCKERHUB)/chat-enigma:$(TAG)


