// build_params.groovy - Functions for manipulating build parameters
//

@NonCPS
def modify_build_parameter(String key, String value) {
    def build = currentBuild.rawBuild
    def params_list = new ArrayList<StringParameterValue>()
    params_list.add(new StringParameterValue(key, value))
    def new_params_action = null
    def old_params_action = build.getAction(ParametersAction.class)
    if (old_params_action != null) {
        // We need to keep old params
        build.actions.remove(old_params_action)
        new_params_action = old_params_action.createUpdated(params_list)
    } else {
        new_params_action = new ParametersAction(params_list)
    }
    build.actions.add(new_params_action)
}


// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
