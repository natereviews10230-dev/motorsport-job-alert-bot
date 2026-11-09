                notify_ntfy_summary(
                    new_alert_jobs,
                    alert_fingerprints,
                    session,
                    timeout,
                    summary_kind="new",
                    max_bytes=summary_max_bytes,
                )
                alerted = len(new_alert_jobs)
            except Exception:
                notification_succeeded = False
                logging.exception("New-jobs ntfy summary failed")
    else:
        # Individual mode or a non-ntfy configuration. Avoid duplicating console
        # output when it was already printed above.
        delivery_channels = [
            c for c in channels if str(c).casefold() != "console"
        ]
        if not delivery_channels and "console" in normalized_channels:
            alerted = len(new_alert_jobs)
        else:
            for job in new_alert_jobs:
                try:
                    send_notifications(job, delivery_channels, session, timeout)
                    alerted += 1
                except Exception:
                    notification_succeeded = False
                    logging.exception(
                        "Notification failed; job will remain unseen: %s", job.title
                    )

    # First-run baseline jobs were never supposed to alert, so they can always be
    # recorded. Jobs that required a notification are only recorded after the
    # required notification path succeeds, preventing silent lost alerts.
    for job in baseline_jobs:
        store.record(job)
    for job in new_alert_jobs:
        if notification_succeeded:
            store.record(job)

    # Existing jobs that are already seen do not need a write. A newly-added
    # source may be initialized even if notification failed: its unseen jobs will
    # still qualify as new on the next run because they were deliberately not recorded.
    for source_name in sources_to_initialize:
        store.mark_source_initialized(source_name)

    return found, alerted, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor company career pages")
    parser.add_argument("--config", default="config.json", help="Config JSON path")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--preview", action="store_true", help="Print current matches; do not save")
    parser.add_argument(
        "--summary-current",
        action="store_true",
        help="Send one ntfy summary of every current match on this run",
    )
    parser.add_argument("--validate", action="store_true", help="Validate config and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        config = load_config(config_path)
    except Exception as exc:
        logging.error("Invalid config: %s", exc)
        return 2
    if args.validate:
        print(f"Valid config: {config_path}")
        return 0

    state_path = Path(config.get("state_database", "job_alerts.sqlite3"))
    if not state_path.is_absolute():
        state_path = config_path.parent / state_path

    session = build_session(config)
    store = StateStore(state_path)
    interval = int(config.get("poll_interval_seconds", 60))
    try:
        while True:
            started = time.monotonic()
            found, alerted, failures = run_cycle(
                config,
                store,
                session,
                preview=args.preview,
                summary_current=args.summary_current,
            )
            logging.info(
                "Cycle complete: %d current matches; %d new alerts; %d source failures",
                found,
                alerted,
                failures,
            )
            if args.once or args.preview:
                return 1 if failures == len([s for s in config["sources"] if s.get("enabled", True)]) else 0
            elapsed = time.monotonic() - started
            time.sleep(max(1, interval - elapsed))
    except KeyboardInterrupt:
        logging.info("Stopped by user")
        return 0
    finally:
        store.close()
        session.close()


if __name__ == "__main__":
    sys.exit(main())
