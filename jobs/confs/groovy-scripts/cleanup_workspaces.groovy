import java.io.*;
import java.lang.*;
import hudson.model.*;
import hudson.util.*;
import jenkins.model.*;
import hudson.FilePath.FileCallable;
import hudson.slaves.OfflineCause;
import hudson.node_monitors.*;


def runOnSlave(node, cmd, workspace='/tmp') {
  launcher = node.createLauncher(listener)
  // By the docs it seems I have to call this
  launcher.decorateFor(node)
  procLauncher = launcher.launch()
  procLauncher = procLauncher.cmdAsSingleString(cmd)
  procLauncher.readStdout()
  procLauncher.readStderr()

  proc = procLauncher.start()
  res = proc.join()
  stdout = proc.getStdout().text
  stderr = proc.getStderr().text

  if (res != 0) {
    println("ERROR::${workspace}:: cmd: ${cmd}")
    println("ERROR::${workspace}:: rc: ${res}")
    println("ERROR::${workspace}:: stdout: ${stdout}")
    println("ERROR::${workspace}:: stderr: ${stderr}")
    throw new Exception("Failed to run ${cmd}")
  }
  return stdout
}


def workspaceIsIn(ws, wsList) {
  wsPath = ws.toURI().getPath()
  for (wsItem in wsList) {
    wsItemPath = wsItem.toURI().getPath()
    if (wsItemPath.startsWith(wsPath)) {
      return true
    }
  }
  return false
}


curJobURL = build.getEnvironment(listener)['BUILD_URL']

for (node in Jenkins.instance.nodes) {
  computer = node.toComputer()
  // Skip disconnected nodes
  if (computer.getChannel() == null) continue

  rootPath = node.getRootPath()

  size = DiskSpaceMonitor.DESCRIPTOR.get(computer).size
  roundedSize = size / (1024 * 1024 * 1024) as int

  println("\n======")
  println("INFO::node: ${node.getDisplayName()}, free space: ${roundedSize}GB")
  if (roundedSize < 10) {

    // If the slave is already offline, don't change it but if not, set
    // it offline to avoid new jobs from getting in
    wasOnline = computer.isOnline()
    if (wasOnline) {
      reason = new hudson.slaves.OfflineCause.ByCLI(
        "workspace cleanup (${curJobURL})")
      computer.setTemporarilyOffline(true, reason)
      computer.waitUntilOffline()
    } else {
      println("INFO::Node already offline.")
    }

    // get the list of currently used workspaces (to avoid deleting them)
    lockedWorkspaces = []
    executors = computer.getExecutors()
    if (executors != null) {
      for (executor in executors) {
        try {
          curWorkspace = executor.getCurrentWorkspace()
          if (curWorkspace != null) {
            lockedWorkspaces.add(curWorkspace)
            println("INFO::CURRENTLY RUNNING::${curWorkspace.toURI().getPath()}")
          }
        } catch (all) {
        }
      }
    }
    // one off executors also have workspace
    oneOffExecutors = computer.getOneOffExecutors()
    if (oneOffExecutors != null) {
      for (executor in oneOffExecutors) {
        try {
          curWorkspace = executor.getCurrentWorkspace()
          if (curWorkspace != null) {
            lockedWorkspaces.add(curWorkspace)
            println("INFO::CURRENTLY RUNNING::${curWorkspace.toURI().getPath()}")
          }
        } catch (all) {
          // Sometimes it seems it throws NullPointerexception, but we
          // don't care as that only happens when the executor is not
          // running anything, so just ignore it
        }
      }
    }

    baseWorkspace = rootPath.child('workspace')
    mounts = 'not_checked'
    for (jobWorkspace in baseWorkspace.listDirectories()) {
      pathAsString = jobWorkspace.getRemote()
      // not sure if this ever happens
      if (!jobWorkspace.exists()) {
        continue
      }
      if (workspaceIsIn(jobWorkspace, lockedWorkspaces)) {
        println("INFO::" + jobWorkspace + "::SKIPPING:: Currently in use")
      } else {
        try {
          println("INFO::${jobWorkspace}:: Wiping out")
          println("INFO::${jobWorkspace}:: Making sure there are no mounts")
          if (mounts == 'not_checked') {
            mounts = runOnSlave(node, 'mount')
          }
          mounts.eachLine { mount ->
            if (mount.length() > 3) {
             mountPath = mount.split(' ')[2]
              if (mountPath.startsWith(wsPath)) {
                println("WARN::${wsPath}:: Found stalled mount ${mountPath}, trying to umount")
                runOnSlave(node, "sudo umount '${mountPath}'")
              }
            }
          }
          try {
            jobWorkspace.deleteRecursive()
          } catch (IOException) {
            wsPath = jobWorkspace.toURI().getPath()
            if (wsPath != '/') {
              println("WARN::${wsPath}:: It seems we can't remove as default user... sudoing!")
              runOnSlave(node, "sudo rm -Rf '${wsPath}'")
            }
          }
          println("INFO::" + wsPath + ":: Deleted")
        } catch (Exception) {
          println("ERROR::${node.getDisplayName()}:: Failed to remove workspace ${wsPath}")
        }
      }
    }

    // take it back online if it was online before so it can keep
    // running new jobs
    if (wasOnline) {
      computer.setTemporarilyOffline(false, null)
      computer.waitUntilOnline()
    }
  }
}
println("======")
