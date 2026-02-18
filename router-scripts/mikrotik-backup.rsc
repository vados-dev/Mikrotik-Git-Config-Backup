# MikroTik Git Config Backup
# Edit the three variables below, then add this script under System > Scripts

:local serverUrl "http://192.168.1.10:8080"
:local authToken "change-me-use-a-long-random-string"
:local routerName [/system identity get name]

:put "git-backup: starting for $routerName"
:log info "git-backup: starting for $routerName"

:put "git-backup: checking server..."
:do {
    /tool fetch url=($serverUrl . "/health") output=none
    :put "git-backup: server ok"
} on-error={
    :put "git-backup: ERROR cannot reach $serverUrl"
    :log error "git-backup: cannot reach $serverUrl"
    :error "unreachable"
}

:put "git-backup: exporting config..."
/export show-sensitive file=git-backup-config
:delay 3s

:put "git-backup: uploading .rsc..."
:do {
    :local rscContent [/file get [/file find name="git-backup-config.rsc"] contents]
    :local headers ("Authorization: Bearer " . $authToken . ",X-Router-Name: " . $routerName)
    /tool fetch url=($serverUrl . "/backup/config") http-method=post http-header-field=$headers http-data=$rscContent output=user
    :put "git-backup: .rsc done"
} on-error={
    :put "git-backup: ERROR .rsc upload failed"
    :log error "git-backup: .rsc upload failed"
}

:do { /file remove [find name="git-backup-config.rsc"] } on-error={}

:put "git-backup: done"
:log info "git-backup: done"
