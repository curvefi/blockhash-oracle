# 🔗 Blockhash Oracle Web Dashboard

A modern, real-time web interface for monitoring and interacting with the deployed blockhash oracle system. Built with pure HTML/JS for simplicity and portability.

## ✨ Features

### Core Functionality
- **📈 Real-time Monitoring**: Live updates of all deployed oracles with block synchronization status
- **🚦 Visual Status Indicators**:
  - 🟢 Green: Synced (< 100 blocks behind)
  - 🟡 Yellow: Active but lagging (> 100 blocks behind)
  - 🔴 Red: No confirmed blocks yet
- **📊 Statistics Dashboard**:
  - Main chain current block height
  - Active oracles count
  - Read-enabled chains
  - Average lag across all chains
  - Total deployed chains

### Interactive Operations
- **🔍 Request Block**: Fetch latest block from Ethereum mainnet via LayerZero Read
- **📡 Broadcast**: Send confirmed blocks to all configured peer chains
- **📄 Submit Header**: Enable state proof verification (coming soon)
- **🔗 Peer Connections**: View which chains are connected to each other

### User Experience
- **🤝 MetaMask Integration**: Direct wallet connection for transactions
- **🎯 Filtering**: Filter by active oracles or read-enabled chains
- **⏰ Auto-refresh**: Data updates every 30 seconds
- **📱 Mobile Responsive**: Works on all device sizes
- **🎨 Dark Theme**: Easy on the eyes for extended monitoring

## Setup

The dashboard reads directly from your deployment files, so no additional configuration is needed.

### 1. Serve the UI

**Important**: Serve from the project root directory, NOT from the UI folder!

```bash
# Option 1: Python 3 (most common)
cd /path/to/blockhash-oracle
python -m http.server 8000
# Then navigate to http://localhost:8000/UI/

# Option 2: Python 2
cd /path/to/blockhash-oracle
python -m SimpleHTTPServer 8000
# Then navigate to http://localhost:8000/UI/

# Option 3: Node.js with http-server
cd /path/to/blockhash-oracle
npx http-server -p 8000 --cors
# Then navigate to http://localhost:8000/UI/

# Option 4: PHP built-in server
cd /path/to/blockhash-oracle
php -S localhost:8000
# Then navigate to http://localhost:8000/UI/

# Option 5: VS Code Live Server extension
# Open the project root in VS Code
# Right-click on UI/index.html → "Open with Live Server"
```

### 2. Access the Dashboard

Open http://localhost:8000/UI/ in your browser (note the /UI/ at the end).

## File Structure

```
blockhash-oracle/           # ← Serve from here!
├── UI/
│   ├── index.html         # Main HTML structure and styling
│   ├── app.js             # Application logic and Web3 interactions
│   ├── favicon.svg        # Dashboard icon
│   └── README.md          # This file
└── scripts/
    ├── deployment/
    │   ├── deployment_state.json  # Contract addresses
    │   └── lz_metadata.json       # LayerZero chain metadata
    └── chain-parse/
        └── chains.json            # Chain configurations and RPC URLs
```

## 🚀 Usage Guide

### Dashboard Overview

#### Status Indicators
Each chain card has a colored status dot:
- **🟢 Green (pulsing)**: Oracle is synced and healthy
- **🟡 Yellow (pulsing)**: Oracle is active but lagging behind
- **🔴 Red**: Oracle hasn't received any blocks yet

#### Chain Information
- **EID**: LayerZero Endpoint ID (top-right corner)
- **Block Number**: Last confirmed block from mainnet
- **Block Hash**: Click to copy the full hash
- **Progress Bar**: Visual representation of sync status
- **Connected Peers**: Shows which chains this oracle can send to

#### Badges
- **MAIN**: This is the source chain (Ethereum mainnet/Sepolia)
- **READ**: Chain supports LayerZero Read protocol

### 🔧 Operations

#### 1. Request Block (READ-enabled chains only)
Fetch the latest block from Ethereum mainnet:
- **Basic Request**: Just fetch the block for this chain
- **Request + Broadcast**: Fetch and immediately send to all peers
- Fee is calculated dynamically based on gas costs

#### 2. Broadcast
Send this chain's latest confirmed block to all connected peers:
- Available when the chain has confirmed blocks
- Shows total fee for broadcasting to all peers
- Useful for keeping peer chains in sync

#### 3. Submit Header
Submit block header for state proof verification:
- Available when state root is missing
- Enables on-chain verification of block data
- Currently in development

### 🎯 Filtering & Controls

- **Network Selector**: Switch between Mainnet and Testnet deployments
- **Active Only**: Show only chains with confirmed blocks
- **Read-Enabled Only**: Show only chains with LayerZero Read
- **Refresh Button**: Manual data refresh (also in floating button)
- **Auto-refresh**: Automatic updates every 30 seconds

## Technical Details

### Architecture

#### Chain Identification
The dashboard intelligently matches chains:
- Deployment data uses chain names (e.g., "ethereum", "optimism")
- LayerZero metadata uses chainKey for matching
- Automatic resolution of endpoint IDs and configurations

#### RPC Strategy
Smart RPC selection with fallbacks:
1. **Testnets**: Direct RPC URL from config
2. **Mainnets** (in priority order):
   - Public RPC endpoints
   - DRPC endpoints (API key stripped)
   - Ankr endpoints (API key stripped)

#### Contract Interactions
- **Library**: ethers.js v5 (loaded from CDN)
- **ABIs**: Minimal, function-specific ABIs for efficiency
- **Gas Estimation**: Automatic with configurable buffers
- **Error Recovery**: Graceful handling with user feedback

#### Data Flow
1. Load deployment state from local JSON files
2. Fetch LayerZero metadata for chain configurations
3. Query each chain's RPC for oracle status
4. Aggregate peer connections
5. Update UI with real-time data

### Performance

- **Parallel Loading**: All chain data fetched concurrently
- **Efficient Updates**: Only changed elements re-render
- **Lightweight**: No framework dependencies
- **Caching**: Browser caches static assets

## Security Notes

- The dashboard only reads from public RPCs
- All transactions go through your connected wallet
- No private keys or sensitive data are stored
- Contract addresses are read from local deployment files

## Browser Support

Works best on:
- Chrome/Brave (recommended)
- Firefox
- Safari
- Edge

Requires MetaMask or compatible Web3 wallet for transactions.

## 🔧 Troubleshooting

### Common Issues

#### "Failed to load deployment data"
- **Cause**: Can't find deployment files (usually wrong serving directory)
- **Fix**:
  - **IMPORTANT**: Run the server from the project root, NOT from UI/
  - Correct: `cd /path/to/blockhash-oracle && python -m http.server 8000`
  - Wrong: `cd /path/to/blockhash-oracle/UI && python -m http.server 8000`
  - Verify these files exist:
    - `scripts/deployment/deployment_state.json`
    - `scripts/deployment/lz_metadata.json`
    - `scripts/chain-parse/chains.json`

#### "Please install MetaMask"
- **Cause**: No Web3 wallet detected
- **Fix**:
  1. Install [MetaMask](https://metamask.io/) browser extension
  2. Create or import a wallet
  3. Refresh the dashboard page

#### Transaction Failures
- **Wrong Network**:
  - Switch MetaMask to the correct network
  - Match the network selector in the dashboard
- **Insufficient Balance**:
  - Ensure you have enough ETH for gas fees
  - Request/broadcast operations typically cost 0.001-0.01 ETH
- **Contract Error**:
  - Check deployment addresses are correct
  - Verify contracts are deployed on the target chain

#### No Chains Displaying
1. **Open browser console** (F12 → Console tab)
2. **Look for red errors** indicating:
   - Missing files
   - CORS issues (use proper HTTP server)
   - Invalid JSON format
3. **Verify deployment data**:
   ```javascript
   // In browser console:
   fetch('../scripts/deployment/deployment_state.json')
     .then(r => r.json())
     .then(console.log)
   ```

#### Slow Loading
- **RPC Issues**: Some public RPCs may be slow
- **Network**: Check your internet connection
- **Browser**: Try Chrome/Brave for best performance

### Debug Mode

Enable verbose logging in browser console:
```javascript
// Paste in browser console
localStorage.setItem('debug', 'true');
location.reload();
```

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📝 License

Part of the Blockhash Oracle project.
