# Sourced by devenv/run and devenv/conary_test_baseline.sh (ROOT must be set).
# Resolves the conary-policy checkout and sets:
#   policy_args  docker args: -v <checkout>:/policy:ro -e CONARY_POLICY_PATH=/policy/policy
#                (empty when there is no checkout)
#   policy_head  `git describe --always --dirty` of the checkout, or "absent"
# CONARY_POLICY_SRC overrides the default $ROOT/../conary-policy; an explicit
# override that is missing or unsafe is an error (exit 2), a missing default is not.
policy_args=()
policy_head=absent
_policy_explicit=0
if [ -n "${CONARY_POLICY_SRC:-}" ]; then
    _policy_explicit=1
    _policy_src=$CONARY_POLICY_SRC
else
    _policy_src=$ROOT/../conary-policy
fi
case "$_policy_src" in
    *[!A-Za-z0-9._/-]*)
        echo "devenv: unsafe conary-policy path (allowed: A-Za-z0-9._/-): $_policy_src" >&2
        exit 2;;
esac
if [ -d "$_policy_src/policy" ]; then
    _policy_src=$(cd "$_policy_src" && pwd -P)
    case "$_policy_src" in
        *[!A-Za-z0-9._/-]*)
            echo "devenv: unsafe conary-policy path (allowed: A-Za-z0-9._/-): $_policy_src" >&2
            exit 2;;
    esac
    policy_args=(-v "$_policy_src":/policy:ro -e CONARY_POLICY_PATH=/policy/policy)
    policy_head=$(git -C "$_policy_src" describe --always --dirty 2>/dev/null || echo unknown)
elif [ "$_policy_explicit" = 1 ]; then
    echo "devenv: CONARY_POLICY_SRC has no policy/ directory: $_policy_src" >&2
    exit 2
else
    echo "devenv: no conary-policy checkout at $_policy_src; CONARY_POLICY_PATH not set" >&2
fi
unset _policy_src _policy_explicit
