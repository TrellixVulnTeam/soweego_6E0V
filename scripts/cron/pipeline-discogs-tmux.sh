cd /srv/dryrun/soweego/
/usr/bin/tmux kill-session -t pipeline-discogs
/usr/bin/tmux new-session -d -s "pipeline-discogs" ./scripts/docker/launch_pipeline.sh -c ../prod_cred.json -s /srv/dryrun/shared/ discogs --no-upload --validator
