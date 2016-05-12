import java.io.*;
import java.lang.*;
import hudson.model.*;
import hudson.util.*;
import jenkins.model.*;
import hudson.FilePath.FileCallable;
import hudson.slaves.OfflineCause;
import hudson.node_monitors.*;
import hudson.model.queue.Executables;


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
jobSkipList = build.getEnvironment(listener)['SKIP_JOBS']
jobSkipList = jobSkipList.replace(',', ' ').split(' ')
nodeSkipList = build.getEnvironment(listener)['SKIP_NODES']
nodeSkipList = nodeSkipList.replace(',', ' ').split(' ')

for (node in Jenkins.instance.nodes) {
  // Sometimes node is not what we expect
  try {
    computer = node.toComputer()
    // Skip disconnected node
    if (computer.getChannel() == null) {
        println("\n======")
        println("INFO::Skipping ${node.getDisplayName()}, not connected.")
        continue
    }

    if (node.getDisplayName() in nodeSkipList) {
        println("\n======")
        println("INFO::Skipping ${node.getDisplayName()}, in the skip list.")
        continue
    }
    rootPath = node.getRootPath()

    size = DiskSpaceMonitor.DESCRIPTOR.get(computer).size
    roundedSize = size / (1024 * 1024 * 1024) as int

  } catch (Exception exc) {
    exc.printStackTrace()
    continue
  }

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
    //add also the workspaces of the skipped jobs, if any
    lockedWorkspaces = []
    println('getting executors')
    executors = computer.getExecutors()
    println('got executors')
    if (executors != null) {
      for (executor in executors) {
        //try {
          if (executor == null){
            println('Empty executor!')
            continue
          }
          if (executor.isIdle()) {
            continue
          }
          println('getting build')
          println(executor)
          println(executor.getDisplayName())
          try {
            build = executor.getCurrentExecutable()
          } catch (all) {
            println('Exception getting build from executor')
            println(executor)
            println(all)
            throw all
          }
          println('got build')
          if (build == null) {
            continue
          }
          parent = Executables.getParentOf(build)
          println('got parent')
          if (parent == null) {
            continue
          }
          task = parent.getOwnerTask()
          println('got task')
          if (task == null) {
            continue
          }
          name = task.getName()
          println('got name')
          curWorkspace = executor.getCurrentWorkspace()
          if (name in jobSkipList) {
            lockedWorkspaces.add(curWorkspace)
            println("INFO::SKIPPING::IN JOB SKIP LIST::${curWorkspace.toURI().getPath()}")
            continue
          }
          if (curWorkspace == null) {
            continue
          }
          lockedWorkspaces.add(curWorkspace)
          println("INFO::SKIPPING::CURRENTLY RUNNING::${curWorkspace.toURI().getPath()}")
//        } catch (all) {
//          println('Got exception!!!!!!')
//          println(all)
//        }
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
        continue
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
                runOnSlave(node, "sudo umount --lazy '${mountPath}'")
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

