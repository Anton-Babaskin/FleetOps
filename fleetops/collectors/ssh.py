# ruff: noqa: E501
import asyncio
import shlex
from collections.abc import Awaitable, Callable
from time import monotonic

import asyncssh

from fleetops.checks.disk import parse_df
from fleetops.checks.load import parse_loadavg
from fleetops.checks.memory import parse_meminfo
from fleetops.checks.systemd import parse_systemctl_failed
from fleetops.config import AppConfig, EnvSettings
from fleetops.domain.models import CheckResult, HostIdentity
from fleetops.rules.health import (
    evaluate_disk,
    evaluate_load,
    evaluate_memory,
    evaluate_systemd,
    run_timed_check,
    unknown_check,
)


class SSHCommandError(RuntimeError):
    pass


MAIL_SCRIPT_HELPERS = r"""
mail_since_seconds() {
  case "${FLEETOPS_MAIL_SINCE:-}" in
    "") return 1 ;;
    *m) echo "$(( ${FLEETOPS_MAIL_SINCE%m} * 60 ))" ;;
    *h) echo "$(( ${FLEETOPS_MAIL_SINCE%h} * 3600 ))" ;;
    *d) echo "$(( ${FLEETOPS_MAIL_SINCE%d} * 86400 ))" ;;
    *) return 1 ;;
  esac
}

mail_stream() {
  if ls /var/log/mail.log* >/dev/null 2>&1; then
    for file in $(ls -1tr /var/log/mail.log* 2>/dev/null | tail -n 8); do
      case "$file" in
        *.gz) zcat -f "$file" 2>/dev/null ;;
        *) cat "$file" 2>/dev/null ;;
      esac
    done
  else
    journal_since="7 days ago"
    if seconds=$(mail_since_seconds); then
      journal_since="$seconds seconds ago"
    fi
    timeout 5s journalctl -u postfix --since "$journal_since" --no-pager --output=short-iso 2>/dev/null
  fi
}

filter_since() {
  if ! seconds=$(mail_since_seconds); then
    cat
    return
  fi
  cutoff=$(date -d "$seconds seconds ago" +%s 2>/dev/null || echo 0)
  year=$(date +%Y)
  awk -v cutoff="$cutoff" -v year="$year" '
    BEGIN {
      month["Jan"]=1; month["Feb"]=2; month["Mar"]=3; month["Apr"]=4;
      month["May"]=5; month["Jun"]=6; month["Jul"]=7; month["Aug"]=8;
      month["Sep"]=9; month["Oct"]=10; month["Nov"]=11; month["Dec"]=12;
    }
    /^[A-Z][a-z][a-z][ ]+[0-9]+ [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ {
      split($3, t, ":");
      epoch=mktime(year " " month[$1] " " $2 " " t[1] " " t[2] " " t[3]);
      if (epoch >= cutoff) print;
      next;
    }
    /^[0-9][0-9][0-9][0-9]-/ {
      print;
      next;
    }
    cutoff <= 0 { print; }
  '
}
"""


class SSHCollector:
    def __init__(self, config: AppConfig, env: EnvSettings) -> None:
        if env.ssh_known_hosts_path is None:
            raise ValueError("FLEETOPS_SSH_KNOWN_HOSTS_PATH is required for SSH mode")
        self.config = config
        self.env = env
        self.host = HostIdentity(id=config.host.id, hostname=config.host.hostname)

    def _bash_script(self, script: str, **env: str | int | None) -> str:
        assignments = " ".join(
            f"{key}={shlex.quote(str(value))}"
            for key, value in env.items()
            if value is not None
        )
        prefix = f"{assignments} " if assignments else ""
        return f"{prefix}bash <<'FLEETOPS_BASH'\n{script}\nFLEETOPS_BASH"

    async def collect_health(self) -> list[CheckResult]:
        try:
            conn = await self._connect()
        except Exception as exc:
            return [
                unknown_check(
                    name=name,
                    summary=f"{name.capitalize()} check failed",
                    error=f"SSH connection failed: {type(exc).__name__}: {exc}",
                    duration_ms=0,
                )
                for name in ("load", "memory", "disk", "systemd")
            ]
        async with conn:
            checks = [
                run_timed_check(
                    "load",
                    lambda: self._load(conn),
                    self.config.timeouts.command_seconds,
                ),
                run_timed_check(
                    "memory",
                    lambda: self._memory(conn),
                    self.config.timeouts.command_seconds,
                ),
                run_timed_check(
                    "disk",
                    lambda: self._disk(conn),
                    self.config.timeouts.command_seconds,
                ),
                run_timed_check(
                    "systemd",
                    lambda: self._systemd(conn),
                    self.config.timeouts.command_seconds,
                ),
            ]
            return list(await asyncio.gather(*checks))

    async def collect_snapshot(self) -> list[tuple[str, str]]:
        commands = [
            "hostname",
            "date",
            "uptime",
            "free -h",
            "df -h",
            "df -i",
            "systemctl --failed --no-pager",
            "journalctl -p err -n 100 --no-pager",
            "dmesg --level=err,warn",
        ]
        sections: list[tuple[str, str]] = []
        try:
            conn = await self._connect()
        except Exception as exc:
            return [("ssh connection", f"ERROR: {type(exc).__name__}: {exc}")]
        async with conn:
            for command in commands:
                try:
                    output = await self._run(conn, command)
                except Exception as exc:
                    output = f"ERROR: {type(exc).__name__}: {exc}"
                sections.append((command, output))
        return sections

    async def collect_services(self) -> str:
        command = (
            "systemctl list-units --type=service --state=running,failed "
            "--no-pager --no-legend"
        )
        return await self._collect_report(command)

    async def collect_journal(self) -> str:
        command = "journalctl -p warning -n 40 --no-pager --output=short-iso"
        return await self._collect_report(command)

    async def collect_ports(self) -> str:
        command = "ss -H -tulpen | head -n 80"
        return await self._collect_report(command)

    async def collect_docker(self) -> str:
        command = (
            "if command -v docker >/dev/null 2>&1; then "
            "echo '## docker ps'; "
            "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'; "
            "echo; echo '## docker system df'; docker system df; "
            "else echo 'Docker is not installed or not in PATH.'; fi"
        )
        return await self._collect_report(command)

    async def collect_mail(self) -> str:
        command = (
            "for svc in postfix dovecot nginx opendkim opendmarc spamassassin "
            "postgrey mailinabox; do "
            "if systemctl list-unit-files \"$svc.service\" >/dev/null 2>&1; then "
            "printf '%s.service ' \"$svc\"; systemctl is-active \"$svc.service\"; "
            "fi; "
            "done"
        )
        return await self._collect_report(command)

    async def collect_mail_queue(self) -> str:
        command = (
            "if command -v postqueue >/dev/null 2>&1; then "
            "postqueue -p | tail -n 80; "
            "else echo 'postqueue is not installed or not in PATH.'; fi"
        )
        return await self._collect_report(command)

    async def collect_mail_dns(self) -> str:
        command = (
            "host=$(hostname -f 2>/dev/null || hostname); "
            "domain=$(postconf -h mydomain 2>/dev/null || true); "
            "echo \"## identity\"; echo \"hostname=$host\"; "
            "if [ -n \"$domain\" ]; then echo \"postfix_mydomain=$domain\"; fi; "
            "if [ -f /etc/mailinabox.conf ]; then "
            "grep -E '^(PRIMARY_HOSTNAME|PUBLIC_IP|PUBLIC_IPV6)=' "
            "/etc/mailinabox.conf || true; fi; "
            "echo; echo '## DNS'; "
            "for name in $host $domain; do "
            "if [ -n \"$name\" ]; then "
            "echo \"### $name\"; "
            "if command -v dig >/dev/null 2>&1; then "
            "echo 'MX:'; dig +short MX \"$name\"; "
            "echo 'A:'; dig +short A \"$name\"; "
            "echo 'AAAA:'; dig +short AAAA \"$name\"; "
            "echo 'SPF:'; dig +short TXT \"$name\" | grep -i spf || true; "
            "echo 'DMARC:'; dig +short TXT \"_dmarc.$name\" || true; "
            "else echo 'dig is not installed.'; fi; "
            "fi; done"
        )
        return await self._collect_report(command)

    async def collect_mail_tls(self) -> str:
        command = (
            "echo '## postfix'; "
            "cert=$(postconf -h smtpd_tls_cert_file 2>/dev/null || true); "
            "echo \"smtpd_tls_cert_file=$cert\"; "
            "if [ -n \"$cert\" ] && [ -r \"$cert\" ]; then "
            "openssl x509 -in \"$cert\" -noout -subject -issuer -dates; "
            "else echo 'postfix certificate file is not readable'; fi; "
            "echo; echo '## dovecot'; "
            "dcert=$(doveconf -h ssl_cert 2>/dev/null | sed 's/^<//'); "
            "echo \"ssl_cert=$dcert\"; "
            "if [ -n \"$dcert\" ] && [ -r \"$dcert\" ]; then "
            "openssl x509 -in \"$dcert\" -noout -subject -issuer -dates; "
            "else echo 'dovecot certificate file is not readable'; fi"
        )
        return await self._collect_report(command)

    async def collect_mail_logs(self, since: str | None = None) -> str:
        command = self._bash_script(
            MAIL_SCRIPT_HELPERS
            + r"""
set +e
mail_stream \
  | tail -n 20000 \
  | filter_since \
  | grep -E "NOQUEUE: reject|reject: RCPT|status=(sent|bounced|deferred)" \
  | tail -n 100 || true
""",
            FLEETOPS_MAIL_SINCE=since,
        )
        return await self._collect_report(command)

    async def collect_mail_rejections(self, since: str | None = None) -> str:
        command = self._bash_script(
            MAIL_SCRIPT_HELPERS
            + r"""
set +e
mail_stream \
  | tail -n 20000 \
  | filter_since \
  | grep -E "NOQUEUE: reject|reject: RCPT" \
  | tail -n 80 || true
""",
            FLEETOPS_MAIL_SINCE=since,
        )
        return await self._collect_report(command)

    async def collect_mail_delivery(self, since: str | None = None) -> str:
        command = self._bash_script(
            MAIL_SCRIPT_HELPERS
            + r"""
set +e
mail_stream \
  | tail -n 20000 \
  | filter_since \
  | grep -E "status=(sent|bounced|deferred)" \
  | tail -n 80 || true
""",
            FLEETOPS_MAIL_SINCE=since,
        )
        return await self._collect_report(command)

    async def collect_mail_stats(self, since: str | None = None) -> str:
        command = self._bash_script(
            MAIL_SCRIPT_HELPERS
            + r"""
set +e
declare -A q_from q_size from_domains to_domains routes relays reject_reasons volume_bytes volume_count
sent=0
deferred=0
bounced=0
rejected=0
greylisted=0
qid_re=": ([A-F0-9]{5,}): "
from_re="from=<([^>]*)>"
to_re="to=<([^>]*)>"
relay_re="relay=([^,]+)"
size_re="size=([0-9]+)"

domain_of() {
  value="$1"
  if [ -z "$value" ]; then
    printf "%s" "unknown"
    return
  fi
  if [[ "$value" == *"@"* ]]; then
    value="${value##*@}"
  fi
  value="${value,,}"
  value="${value%.}"
  printf "%s" "${value:-unknown}"
}

relay_of() {
  value="$1"
  value="${value%%[*}"
  value="${value%%:*}"
  value="${value,,}"
  value="${value%.}"
  printf "%s" "${value:-none}"
}

reason_of() {
  value="$1"
  value="${value%%; from=<*}"
  if [[ "${value,,}" == *"greylisted"* ]]; then
    printf "%s" "Greylisted"
  elif [[ "${value,,}" == *"relay access denied"* ]]; then
    printf "%s" "Relay access denied"
  elif [[ "${value,,}" == *"spamhaus"* ]]; then
    printf "%s" "Spamhaus blocklist"
  elif [[ "${value,,}" == *"sender address rejected"* ]]; then
    printf "%s" "Sender address rejected"
  elif [[ "${value,,}" == *"recipient address rejected"* ]]; then
    printf "%s" "Recipient address rejected"
  elif [ -n "$value" ]; then
    printf "%s" "${value:0:120}"
  else
    printf "%s" "Unknown reject reason"
  fi
}

top_counts() {
  title="$1"
  array_name="$2"
  limit="${3:-10}"
  declare -n data="$array_name"
  echo "== $title =="
  for key in "${!data[@]}"; do
    printf "%s\t%s\n" "${data[$key]}" "$key"
  done | sort -rn | head -n "$limit" | awk -F "\t" "{printf \"%s %s\\n\", \$1, \$2}"
  echo
}

while IFS= read -r line; do
  qid=""
  if [[ "$line" =~ $qid_re ]]; then
    qid="${BASH_REMATCH[1]}"
  fi

  if [[ "$line" == *"postfix/qmgr"* && -n "$qid" ]]; then
    if [[ "$line" =~ $from_re ]]; then
      q_from[$qid]="${BASH_REMATCH[1]}"
    fi
    if [[ "$line" =~ $size_re ]]; then
      q_size[$qid]="${BASH_REMATCH[1]}"
    fi
  fi

  if [[ "$line" == *"status=sent"* || "$line" == *"status=deferred"* || "$line" == *"status=bounced"* ]]; then
    status="sent"
    [[ "$line" == *"status=deferred"* ]] && status="deferred"
    [[ "$line" == *"status=bounced"* ]] && status="bounced"
    case "$status" in
      sent) sent=$((sent + 1)) ;;
      deferred) deferred=$((deferred + 1)) ;;
      bounced) bounced=$((bounced + 1)) ;;
    esac
    to_addr=""
    relay=""
    [[ "$line" =~ $to_re ]] && to_addr="${BASH_REMATCH[1]}"
    [[ "$line" =~ $relay_re ]] && relay="${BASH_REMATCH[1]}"
    from_domain="$(domain_of "${q_from[$qid]}")"
    to_domain="$(domain_of "$to_addr")"
    relay_domain="$(relay_of "$relay")"
    if [ "$status" = "sent" ]; then
      from_domains[$from_domain]=$(( ${from_domains[$from_domain]:-0} + 1 ))
      to_domains[$to_domain]=$(( ${to_domains[$to_domain]:-0} + 1 ))
      relays[$relay_domain]=$(( ${relays[$relay_domain]:-0} + 1 ))
      route="$from_domain -> $to_domain -> $relay_domain"
      routes[$route]=$(( ${routes[$route]:-0} + 1 ))
      size="${q_size[$qid]:-0}"
      if [[ "$size" =~ ^[0-9]+$ ]]; then
        volume_bytes[$from_domain]=$(( ${volume_bytes[$from_domain]:-0} + size ))
        volume_count[$from_domain]=$(( ${volume_count[$from_domain]:-0} + 1 ))
      fi
    fi
  fi

  if [[ "$line" == *"reject: RCPT from"* ]]; then
    rejected=$((rejected + 1))
    tail_part="${line#*reject: RCPT from }"
    if [[ "$tail_part" == *"]: "* ]]; then
      reason="${tail_part#*]: }"
    else
      reason="${tail_part#*: }"
    fi
    reason_key="$(reason_of "$reason")"
    [[ "$reason_key" = "Greylisted" ]] && greylisted=$((greylisted + 1))
    reject_reasons[$reason_key]=$(( ${reject_reasons[$reason_key]:-0} + 1 ))
  fi
done < <(mail_stream | tail -n 20000 | filter_since)

echo "== MAIL STATS SUMMARY =="
echo "sent=$sent"
echo "deferred=$deferred"
echo "bounced=$bounced"
echo "rejected=$rejected"
echo "greylisted=$greylisted"
echo "from_domains=${#from_domains[@]}"
echo "to_domains=${#to_domains[@]}"
echo
top_counts "TOP FROM DOMAINS" from_domains 12
top_counts "TOP TO DOMAINS" to_domains 12
top_counts "TOP ROUTES" routes 10
top_counts "TOP RELAYS" relays 10
top_counts "TOP REJECT REASONS" reject_reasons 10
echo "== TOP VOLUME FROM DOMAINS =="
for key in "${!volume_bytes[@]}"; do
  bytes="${volume_bytes[$key]}"
  count="${volume_count[$key]:-0}"
  awk -v bytes="$bytes" -v count="$count" -v key="$key" "BEGIN {printf \"%.1f MB %s %s\\n\", bytes / 1024 / 1024, count, key}"
done | sort -rn | head -n 10
""",
            FLEETOPS_MAIL_SINCE=since,
        )
        return await self._collect_report(command)

    async def collect_mail_search(
        self,
        *,
        mode: str,
        query: str,
        since: str | None = None,
    ) -> str:
        command = self._bash_script(
            MAIL_SCRIPT_HELPERS
            + r"""
set +e
declare -A q_from
qid_re=": ([A-F0-9]{5,}): "
from_re="from=<([^>]*)>"
to_re="to=<([^>]*)>"
query="${FLEETOPS_MAIL_QUERY,,}"
mode="${FLEETOPS_MAIL_MODE:-any}"

domain_of() {
  value="$1"
  if [[ "$value" == *"@"* ]]; then
    value="${value##*@}"
  fi
  value="${value,,}"
  value="${value%.}"
  printf "%s" "$value"
}

matches_query() {
  line="$1"
  from="$2"
  to="$3"
  lower_line="${line,,}"
  case "$mode" in
    from)
      [[ "${from,,}" == *"$query"* ]]
      ;;
    to)
      [[ "${to,,}" == *"$query"* ]]
      ;;
    ip)
      [[ "$lower_line" == *"$query"* ]]
      ;;
    domain)
      from_domain="$(domain_of "$from")"
      to_domain="$(domain_of "$to")"
      [[ "$from_domain" == *"$query"* || "$to_domain" == *"$query"* || "$lower_line" == *"$query"* ]]
      ;;
    *)
      [[ "$lower_line" == *"$query"* || "${from,,}" == *"$query"* || "${to,,}" == *"$query"* ]]
      ;;
  esac
}

while IFS= read -r line; do
  qid=""
  if [[ "$line" =~ $qid_re ]]; then
    qid="${BASH_REMATCH[1]}"
  fi

  if [[ "$line" == *"postfix/qmgr"* && -n "$qid" && "$line" =~ $from_re ]]; then
    q_from[$qid]="${BASH_REMATCH[1]}"
    continue
  fi

  if [[ "$line" != *"reject: RCPT from"* && "$line" != *"status=sent"* && "$line" != *"status=deferred"* && "$line" != *"status=bounced"* ]]; then
    continue
  fi

  from=""
  to=""
  if [[ "$line" =~ $from_re ]]; then
    from="${BASH_REMATCH[1]}"
  elif [ -n "$qid" ]; then
    from="${q_from[$qid]:-}"
  fi
  if [[ "$line" =~ $to_re ]]; then
    to="${BASH_REMATCH[1]}"
  fi

  output="$line"
  if [ -n "$from" ] && [[ "$output" != *"from=<"* ]]; then
    output="$output from=<$from>"
  fi

  if matches_query "$output" "$from" "$to"; then
    printf "%s\n" "$output"
  fi
done < <(
  mail_stream \
    | tail -n 12000 \
    | filter_since \
    | grep -E "postfix/qmgr.*from=<|reject: RCPT from|status=(sent|bounced|deferred)" || true
) | tail -n 80
""",
            FLEETOPS_MAIL_MODE=mode,
            FLEETOPS_MAIL_QUERY=query,
            FLEETOPS_MAIL_SINCE=since,
        )
        return await self._collect_report(command)

    async def collect_mail_service_logs(self) -> str:
        command = (
            "timeout 5s journalctl -u postfix -u dovecot -u opendkim -u opendmarc "
            "-u postgrey -n 80 --no-pager --output=short-iso | tail -n 80 || true"
        )
        return await self._collect_report(command)

    async def collect_greylist(self) -> str:
        command = r"""bash -lc '
set +e
logs=$(
  {
    timeout 5s journalctl -u postgrey --since "7 days ago" --no-pager -o cat 2>/dev/null
    if ls /var/log/mail.log* >/dev/null 2>&1; then
      if command -v zgrep >/dev/null 2>&1; then
        zgrep -h "postgrey" /var/log/mail.log* 2>/dev/null
      else
        grep -h "postgrey" /var/log/mail.log* 2>/dev/null
      fi
    fi
  } | tail -n 5000
)
events=$(printf "%s\n" "$logs" | grep -Ei "action=|client_address=|greylist,|triplet|delayed|whitelist|reject" || true)
echo "== GREYLIST SUMMARY =="
printf "%s\n" "$events" | grep -Eic "action=greylist|greylist," | awk "{print \"greylisted=\" \$1}"
printf "%s\n" "$events" | grep -Eic "action=pass|triplet found|delayed" | awk "{print \"passed=\" \$1}"
printf "%s\n" "$events" | grep -Eic "action=reject|reject" | awk "{print \"rejected=\" \$1}"
printf "%s\n" "$events" | grep -Eic "whitelist|action=whitelist" | awk "{print \"whitelisted=\" \$1}"
echo
echo "== TOP CLIENT IPs =="
printf "%s\n" "$events" \
  | sed -nE "s/.*client_address=([0-9A-Fa-f:.]+).*/\1/p" \
  | sort | uniq -c | sort -rn | head -n 12
echo
echo "== TOP SENDERS =="
printf "%s\n" "$logs" \
  | sed -nE "s/.*sender=([^, ]+).*/\1/p" \
  | sort | uniq -c | sort -rn | head -n 12
echo
echo "== RECENT EVENTS =="
printf "%s\n" "$events" | tail -n 80
'"""
        return await self._collect_report(command)

    async def collect_top(self) -> str:
        command = "top -b -n 1 | head -n 25"
        return await self._collect_report(command)

    async def collect_processes(self) -> str:
        command = (
            "echo '## CPU'; "
            "ps -eo pid,ppid,user,stat,%cpu,%mem,etime,comm --sort=-%cpu | head -n 16; "
            "echo; echo '## Memory'; "
            "ps -eo pid,ppid,user,stat,%cpu,%mem,etime,comm --sort=-%mem | head -n 16"
        )
        return await self._collect_report(command)

    async def collect_reboots(self) -> str:
        command = "who -b; uptime -p; echo; last -x reboot shutdown | head -n 12"
        return await self._collect_report(command)

    async def collect_updates(self) -> str:
        command = (
            "if command -v apt >/dev/null 2>&1; then "
            "apt list --upgradable 2>/dev/null | head -n 60; "
            "elif command -v dnf >/dev/null 2>&1; then dnf check-update | head -n 60; "
            "elif command -v yum >/dev/null 2>&1; then yum check-update | head -n 60; "
            "elif command -v apk >/dev/null 2>&1; then apk version -l '<' | head -n 60; "
            "else echo 'No supported package manager found.'; fi"
        )
        return await self._collect_report(command)

    async def collect_security(self) -> str:
        command = (
            "echo '## sessions'; who; "
            "echo; echo '## recent logins'; timeout 3s last -n 8 -a || true; "
            "echo; echo '## firewall/services'; "
            "for svc in ufw firewalld fail2ban ssh sshd; do "
            "if systemctl list-unit-files \"$svc.service\" >/dev/null 2>&1; then "
            "printf '%s.service ' \"$svc\"; systemctl is-active \"$svc.service\"; "
            "fi; done; "
            "if command -v ufw >/dev/null 2>&1; then "
            "echo; echo '## ufw'; timeout 3s ufw status | head -n 40 || true; fi"
        )
        return await self._collect_report(command)

    async def collect_docker_logs(self) -> str:
        command = (
            "if command -v docker >/dev/null 2>&1; then "
            "names=$(docker ps --format '{{.Names}}' | head -n 3); "
            "if [ -z \"$names\" ]; then echo 'No running Docker containers.'; "
            "else for name in $names; do echo \"## $name\"; docker logs --tail 30 \"$name\" 2>&1; "
            "echo; done; fi; "
            "else echo 'Docker is not installed or not in PATH.'; fi"
        )
        return await self._collect_report(command)

    async def collect_audit(self) -> str:
        command = r"""bash -lc '
set +e
pass=0; warn=0; critical=0; info=0
say_pass(){ echo "[PASS] $*"; pass=$((pass+1)); }
say_warn(){ echo "[WARN] $*"; warn=$((warn+1)); }
say_critical(){ echo "[CRITICAL] $*"; critical=$((critical+1)); }
say_info(){ echo "[INFO] $*"; info=$((info+1)); }
have(){ command -v "$1" >/dev/null 2>&1; }

echo "== AUDIT CONTEXT =="
echo "date=$(date --iso-8601=seconds 2>/dev/null || date)"
echo "host=$(hostname -f 2>/dev/null || hostname)"
if [ -r /etc/os-release ]; then . /etc/os-release; echo "os=${PRETTY_NAME:-unknown}"; fi
[ "$(id -u)" = "0" ] && say_pass "running as root; local checks have full visibility" || say_warn "not running as root; some checks may be incomplete"
case "$(hostname -f 2>/dev/null || hostname)" in *.*) say_pass "hostname looks like FQDN";; *) say_warn "hostname is not FQDN";; esac

echo
echo "== PATCHES / REBOOT =="
if have apt; then
  updates=$(apt list --upgradable 2>/dev/null | awk "NR>1 {c++} END{print c+0}")
  echo "pending_packages=$updates"
  [ "$updates" -gt 0 ] && say_warn "package updates pending: $updates" || say_pass "no package updates listed by current APT cache"
elif have dnf || have yum || have apk; then
  say_info "non-APT package manager detected; use fleetops updates for package list"
else
  say_info "supported package manager not found"
fi
[ -f /var/run/reboot-required ] && say_warn "reboot-required marker exists" || say_pass "reboot-required marker is absent"

echo
echo "== SSHD CONFIG =="
if have sshd; then
  cfg=$(sshd -T 2>/dev/null || true)
  echo "$cfg" | grep -Ei "^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|kbdinteractiveauthentication|x11forwarding|maxauthtries|authenticationmethods) "
  permit_root=$(printf "%s\n" "$cfg" | awk "\$1==\"permitrootlogin\"{print \$2; exit}")
  pass_auth=$(printf "%s\n" "$cfg" | awk "\$1==\"passwordauthentication\"{print \$2; exit}")
  x11=$(printf "%s\n" "$cfg" | awk "\$1==\"x11forwarding\"{print \$2; exit}")
  if [ "$permit_root" = "yes" ] && [ "$pass_auth" = "yes" ]; then
    say_critical "SSH root login and password authentication are both enabled"
  elif [ "$permit_root" = "yes" ]; then
    say_warn "SSH PermitRootLogin=yes"
  else
    say_pass "SSH direct root login is restricted"
  fi
  [ "$pass_auth" = "yes" ] && say_warn "SSH PasswordAuthentication=yes" || say_pass "SSH password authentication is disabled"
  [ "$x11" = "yes" ] && say_warn "SSH X11Forwarding=yes" || say_pass "SSH X11 forwarding is disabled"
else
  say_warn "sshd effective config is unavailable"
fi

echo
echo "== PUBLIC PORTS / FIREWALL =="
if have ss; then
  ss -H -lntup 2>/dev/null | head -n 80
  allowed="22 25 53 80 110 123 143 443 465 587 993 995 4190 12340"
  unexpected=$(ss -H -lntup 2>/dev/null | awk "{print \$1,\$5}" | while read proto endpoint; do
    case "$endpoint" in 127.*:*|"[::1]":*|::1:*|localhost:*) continue;; esac
    port="${endpoint##*:}"
    echo " $allowed " | grep -q " $port " || echo "$proto $endpoint"
  done | head -n 20)
  if [ -n "$unexpected" ]; then
    say_warn "unexpected non-loopback listeners found"
    printf "%s\n" "$unexpected"
  else
    say_pass "public listeners match the built-in allowlist"
  fi
fi
if have ufw; then
  ufw status | head -n 35
  ufw status | grep -qi "Status: active" && say_pass "UFW is active" || say_warn "UFW is not active"
elif systemctl is-active --quiet firewalld 2>/dev/null; then
  say_pass "firewalld is active"
else
  say_warn "UFW/firewalld not detected as active"
fi

echo
echo "== BRUTE FORCE / AUTH =="
if have fail2ban-client && systemctl is-active --quiet fail2ban 2>/dev/null; then
  fail2ban-client status 2>/dev/null | head -n 30
  say_pass "fail2ban is active"
else
  say_warn "fail2ban is not active"
fi
ssh_failed=$(timeout 4s journalctl -u ssh -u sshd --since "7 days ago" --no-pager -o cat 2>/dev/null | grep -Eic "Failed password|Invalid user|authentication failure" || true)
echo "ssh_failed_events_7d=$ssh_failed"
[ "$ssh_failed" -gt 500 ] && say_warn "high SSH failure count in last 7 days: $ssh_failed" || say_pass "SSH failure count is not high"
mail_failed=$(timeout 4s journalctl -u postfix -u dovecot --since "7 days ago" --no-pager -o cat 2>/dev/null | grep -Eic "SASL.*authentication failed|auth failed|Aborted login|LOGIN FAILED|535" || true)
echo "mail_auth_failures_7d=$mail_failed"
[ "$mail_failed" -gt 2000 ] && say_warn "high mail auth failure count: $mail_failed" || say_pass "mail auth failure count is not high"

echo
echo "== MAIL RELAY / TLS =="
if have postconf; then
  postconf myhostname mydomain mynetworks smtpd_relay_restrictions smtpd_recipient_restrictions smtpd_tls_security_level smtp_tls_security_level 2>/dev/null
  relay=$(postconf -h smtpd_relay_restrictions 2>/dev/null)
  recip=$(postconf -h smtpd_recipient_restrictions 2>/dev/null)
  nets=$(postconf -h mynetworks 2>/dev/null)
  echo "$relay $recip" | grep -Eq "reject_unauth_destination|defer_unauth_destination" && say_pass "Postfix reject/defer_unauth_destination is present" || say_critical "Postfix reject_unauth_destination was not found"
  echo "$nets" | grep -Eq "(^|[ ,])(0\.0\.0\.0/0|0/0|::/0)([ ,]|$)" && say_critical "Postfix mynetworks includes the internet" || say_pass "Postfix mynetworks is not open to the internet"
else
  say_info "postconf not found; postfix relay checks skipped"
fi
if have postqueue; then
  q=$(postqueue -p 2>/dev/null | grep -Ec "^[A-F0-9]+[*!]?[[:space:]]" || true)
  echo "mail_queue_messages=$q"
  [ "$q" -gt 1000 ] && say_critical "very large mail queue: $q" || { [ "$q" -gt 100 ] && say_warn "large mail queue: $q" || say_pass "mail queue size is not high"; }
fi

echo
echo "== LOCAL USERS / FILESYSTEM =="
uid0=$(awk -F: "\$3==0{print \$1}" /etc/passwd 2>/dev/null | tr "\n" " ")
uid0_count=$(awk -F: "\$3==0{c++} END{print c+0}" /etc/passwd 2>/dev/null)
echo "uid0_accounts=$uid0"
[ "$uid0_count" -gt 1 ] && say_critical "multiple UID 0 accounts found" || say_pass "only one UID 0 account"
empty_pw=$(awk -F: "(\$2==\"\"){print \$1}" /etc/shadow 2>/dev/null | tr "\n" " ")
[ -n "$empty_pw" ] && say_critical "accounts with empty password hash: $empty_pw" || say_pass "no empty password hashes found"
nopasswd=$(grep -RhsE "^[[:space:]]*[^#].*NOPASSWD" /etc/sudoers /etc/sudoers.d 2>/dev/null | head -n 20)
[ -n "$nopasswd" ] && { say_warn "sudo NOPASSWD entries found"; printf "%s\n" "$nopasswd"; } || say_pass "sudo NOPASSWD entries not found"
suspicious_suid=$(find /home /root /tmp /var/tmp /dev/shm -xdev -type f -perm -4000 -print 2>/dev/null | head -n 20)
[ -n "$suspicious_suid" ] && { say_critical "SUID files found in user/temp paths"; printf "%s\n" "$suspicious_suid"; } || say_pass "no SUID files in user/temp paths"
world_writable=$(find /etc /usr/local /opt -xdev \( -type f -o -type d \) -perm -0002 -print 2>/dev/null | head -n 20)
[ -n "$world_writable" ] && { say_warn "world-writable objects found in sensitive paths"; printf "%s\n" "$world_writable"; } || say_pass "no world-writable objects in sensitive paths"

echo
echo "== SECURITY FRAMEWORK / BACKUPS =="
if have aa-status; then
  aa-status 2>/dev/null | head -n 25
  say_pass "AppArmor status is available"
elif have getenforce; then
  state=$(getenforce 2>/dev/null || true)
  echo "SELinux=$state"
  [ "$state" = "Enforcing" ] && say_pass "SELinux enforcing" || say_warn "SELinux is not enforcing"
else
  say_info "AppArmor/SELinux status tool not found"
fi
backup_hits=$(for tool in restic borg borgmatic rclone duplicity rsnapshot; do command -v "$tool" 2>/dev/null; done | head -n 10)
if [ -n "$backup_hits" ]; then
  say_info "backup tooling detected"
  printf "%s\n" "$backup_hits"
else
  say_warn "backup tooling not detected locally"
fi

echo
echo "== SUMMARY =="
echo "PASS: $pass"
echo "INFO: $info"
echo "WARN: $warn"
echo "CRITICAL: $critical"
if [ "$critical" -gt 0 ]; then echo "RESULT: CRITICAL"; elif [ "$warn" -gt 0 ]; then echo "RESULT: WARNINGS"; else echo "RESULT: OK"; fi
'"""
        return await self._collect_report(command)

    async def _collect_report(self, command: str) -> str:
        try:
            conn = await self._connect()
        except Exception as exc:
            return f"ERROR: {type(exc).__name__}: {exc}"
        async with conn:
            try:
                return await self._run_report(conn, command)
            except Exception as exc:
                return f"ERROR: {type(exc).__name__}: {exc}"

    async def _connect(self) -> asyncssh.SSHClientConnection:
        kwargs = {
            "host": self.config.host.hostname,
            "port": self.config.host.port,
            "username": self.config.host.username,
            "known_hosts": str(self.env.ssh_known_hosts_path),
            "login_timeout": self.config.timeouts.connection_seconds,
            "connect_timeout": self.config.timeouts.connection_seconds,
        }
        if self.env.ssh_private_key_path is not None:
            kwargs["client_keys"] = [str(self.env.ssh_private_key_path)]
        if self.env.ssh_password is not None:
            kwargs["password"] = self.env.ssh_password
            if self.env.ssh_private_key_path is None:
                kwargs["client_keys"] = []
                kwargs["agent_path"] = None
        return await asyncssh.connect(**kwargs)

    async def _run(self, conn: asyncssh.SSHClientConnection, command: str) -> str:
        result = await conn.run(command, check=False, timeout=self.config.timeouts.command_seconds)
        if result.exit_status != 0:
            stderr = result.stderr.strip() or "remote command failed"
            raise SSHCommandError(stderr[:500])
        return result.stdout

    async def _run_report(self, conn: asyncssh.SSHClientConnection, command: str) -> str:
        result = await conn.run(command, check=False, timeout=self.config.timeouts.command_seconds)
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.exit_status != 0 and not output:
            return f"ERROR: remote command failed with exit status {result.exit_status}"
        return output

    async def _timed_parse(
        self,
        conn: asyncssh.SSHClientConnection,
        command: str,
        parser: Callable[[str], CheckResult] | Callable[[str], Awaitable[CheckResult]],
    ) -> CheckResult:
        started = monotonic()
        output = await self._run(conn, command)
        parsed = parser(output)
        if asyncio.iscoroutine(parsed):
            parsed = await parsed
        parsed.duration_ms = int((monotonic() - started) * 1000)
        return parsed

    async def _load(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        started = monotonic()
        loadavg = await self._run(conn, "cat /proc/loadavg")
        nproc = await self._run(conn, "nproc")
        result = evaluate_load(parse_loadavg(loadavg, nproc), self.config.thresholds.load)
        result.duration_ms = int((monotonic() - started) * 1000)
        return result

    async def _memory(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        return await self._timed_parse(
            conn,
            "cat /proc/meminfo",
            lambda output: evaluate_memory(parse_meminfo(output), self.config.thresholds.memory),
        )

    async def _disk(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        return await self._timed_parse(
            conn,
            "df -B1 -PT",
            lambda output: evaluate_disk(parse_df(output), self.config.thresholds.disk),
        )

    async def _systemd(self, conn: asyncssh.SSHClientConnection) -> CheckResult:
        return await self._timed_parse(
            conn,
            "systemctl --failed --no-legend --no-pager",
            lambda output: evaluate_systemd(
                parse_systemctl_failed(output),
                self.config.thresholds.systemd,
            ),
        )
