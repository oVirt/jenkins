#!/bin/sh

die() {
	local m="${1}"
	echo "FATAL: ${m}"
	exit 1
}

usage() {
	cat << __EOF__
${0} [options]
    --artifacts-directory    artifacts directory
    --help                   prints the usage
__EOF__
}

get_opts() {
	while [ -n "${1}" ]; do
		opt="$1"
		v="${opt#*=}"
		shift
		case "${opt}" in
			--artifacts-directory=*)
				ARTIFACTS_DIR="${v}"
				;;
			--help)
				usage
				exit 0
				;;
			*)
				usage
				die "Wrong option"
				;;
		esac
	done
}

validate() {
	[ -n "${ARTIFACTS_DIR}" ] || die "Please define --artifacts-directory"
	[ -d "${ARTIFACTS_DIR}" ] || die "${ARTIFACTS_DIR} does not exists"
}

get_meta_data() {
	local artifacts_dir="${ARTIFACTS_DIR}"
	local job_name="$(echo "${JOB_NAME}" | sed 's/[/=@]/_/g')"
	local build_number="${BUILD_NUMBER}"

	cat > "${artifacts_dir}/${job_name}-${build_number}.job-metadata" << __EOF__
JOB_NAME="${job_name}"
DATE="$(date +"%Y%m%d")"
__EOF__

	find "${artifacts_dir}" -mindepth 1 -printf "%P\n" > "${artifacts_dir}/${job_name}-${build_number}.job-flist"

}

main() {
	get_opts "${@}"
	validate
	get_meta_data
}

main "${@}"
