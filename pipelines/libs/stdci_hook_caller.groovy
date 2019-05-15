// stdci_hook_caller.groovy - Function for calling hooks from pipelines
//

def on_load(loader) {
    hooks = loader.load_code('libs/stdci_hooks.groovy', this)
}

def withHook(String hook_name, Closure hooked_code) {
    if(hooks.metaClass.respondsTo(hooks, "before_$hook_name")) {
        hooks.metaClass.invokeMethod(hooks, "before_$hook_name")
    }
    if(hooks.metaClass.respondsTo(hooks, "wrap_$hook_name")) {
        hooks.metaClass.invokeMethod(hooks, "wrap_$hook_name") {
            hooked_code()
        }
    } else {
        hooked_code()
    }
    if(hooks.metaClass.respondsTo(hooks, "after_$hook_name")) {
        hooks.metaClass.invokeMethod(hooks, "after_$hook_name")
    }
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
