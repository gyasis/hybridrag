#!/bin/bash
#
# Setup systemd service for .specstory folder watching
# ====================================================
# Creates a systemd service that runs the watcher on boot
# and restarts automatically if it crashes
#
# Usage:
#   sudo ./scripts/setup_systemd_watcher.sh <parent_path> [interval]
#
# Examples:
#   sudo ./scripts/setup_systemd_watcher.sh /home/gyasis/Documents/code
#   sudo ./scripts/setup_systemd_watcher.sh /home/gyasis/Documents/code 300
#

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

PARENT_PATH="${1:-}"
CHECK_INTERVAL="${2:-300}"
CURRENT_USER="${SUDO_USER:-$USER}"
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$PARENT_PATH" ]; then
    echo "Error: Parent path not provided"
    echo ""
    echo "Usage: sudo $0 <parent_path> [interval]"
    echo "Example: sudo $0 /home/gyasis/Documents/code 300"
    exit 1
fi

if [ ! -d "$PARENT_PATH" ]; then
    echo "Error: Parent path does not exist: $PARENT_PATH"
    exit 1
fi

SERVICE_NAME="hybridrag-watcher"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Creating systemd service: $SERVICE_NAME"
echo "  Parent path: $PARENT_PATH"
echo "  Check interval: ${CHECK_INTERVAL}s"
echo "  Run as user: $CURRENT_USER"
echo ""

# Create systemd service file
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=HybridRAG .specstory Folder Watcher
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$HYBRIDRAG_DIR
ExecStart=/bin/bash ${HYBRIDRAG_DIR}/scripts/watch_specstory_folders.sh "$PARENT_PATH" $CHECK_INTERVAL
Restart=always
RestartSec=10
StandardOutput=append:${HYBRIDRAG_DIR}/logs/systemd_watcher.log
StandardError=append:${HYBRIDRAG_DIR}/logs/systemd_watcher.log

# Environment
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

echo "Service file created: $SERVICE_FILE"
echo ""

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service
echo "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

# Start service
echo "Starting service..."
systemctl start "$SERVICE_NAME"

echo ""
echo "✓ Service setup complete!"
echo ""
echo "Useful commands:"
echo "  Check status:  sudo systemctl status $SERVICE_NAME"
echo "  View logs:     sudo journalctl -u $SERVICE_NAME -f"
echo "  Stop service:  sudo systemctl stop $SERVICE_NAME"
echo "  Restart:       sudo systemctl restart $SERVICE_NAME"
echo "  Disable:       sudo systemctl disable $SERVICE_NAME"
echo ""
echo "Log file: ${HYBRIDRAG_DIR}/logs/systemd_watcher.log"
