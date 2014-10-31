#!/usr/bin/env groovy


// Collect all the data
pattern = ~/.*ERROR::([^:]+):: Failed to remove workspace (.+)/
def map = [:]
manager.build.logFile.eachLine { line ->
    matcher = pattern.matcher(line)
    if(matcher.matches()) {
        nodeName = matcher.group(1)
        wsPath = matcher.group(2)
        if (nodeName in map) {
          map[nodeName].add(wsPath)
        } else {
          map[nodeName] = [wsPath]
        }
    }
}

// Create the description entries
if(map.size() > 0) {
    summary = manager.createSummary("warning.gif")
    summary.appendText("Workspaces that failed to cleanup:<ul>", false)
    map.each {
      summary.appendText("<li><b>$it.key</b>:<ul>", false)
      it.value.each {
        summary.appendText("<li>$it</li>", false)
      }
      summary.appendText("</ul></li>", false)
    }
    summary.appendText("</ul>", false)
    manager.addBadge("warning.gif", "Failed to cleanup some workspaces")
}
