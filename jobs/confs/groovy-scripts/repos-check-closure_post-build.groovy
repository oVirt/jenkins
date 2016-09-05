import hudson.model.*
// Add the repo name to the build list
repo=manager.build.buildVariables.get('REPO_NAME')
manager.addShortText("${repo}")

// check if there were uresolved packages/errors
if(manager.logContains(".*unresolved deps:.*")) {
    manager.addWarningBadge("Unresolved dependencies.")
    manager.buildUnstable()
}
if(manager.logContains(".*failure:.*")) {
    manager.buildFailure()
}
