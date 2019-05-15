// stdci_hook_stub.groovy - Empty stub file for use when no hooks are defined
//
// In the STDCI master repo 'libs/stdci_hooks.groovy' would point to this file
// that should remain empty. For repos that inherit from the master repo via
// the upstream-sources mechanism, the symlink can point to a different file
// that would contain hook implementations.

// For convenience, we've documented the supported hook functions that can be
// defined by having stub implementations of them commented out below:

// def before_mock_runner() {
// }

// def wrap_mock_runner(Closure code) {
//    code()
// }

// def after_mock_runner() {
// }

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
