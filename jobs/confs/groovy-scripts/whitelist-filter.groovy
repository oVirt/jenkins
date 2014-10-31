//Set proper status when user not in whitelist
import hudson.model.*
if(manager.logContains(".*NOT FOUND IN THE WHITELIST.*")) {
  manager.build.setResult(Result.NOT_BUILT)
}
