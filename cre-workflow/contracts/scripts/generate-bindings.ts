#!/usr/bin/env bun
// Regenerates the CRE contract bindings from the ABI files in evm/src/abi,
// then patches the raw MainnetBlockView.ts output (see patchMainnetBlockView
// below for why the patch is needed).
import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const contractsDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const projectRoot = join(contractsDir, '..') // cre-workflow/, where project.yaml lives
const mainnetBlockViewPath = join(contractsDir, 'evm/ts/generated/MainnetBlockView.ts')

console.log('> cre generate-bindings evm --language typescript')
execSync('cre generate-bindings evm --language typescript', {
  cwd: projectRoot,
  stdio: 'inherit',
})

patchMainnetBlockView(mainnetBlockViewPath)

// The generator emits one TS method per Vyper `get_blockhash` overload
// (getBlockhash, getBlockhash0, getBlockhash1), but assigns them mismatched
// ABI function names ('get_blockhash0', 'get_blockhash1') that don't exist in
// the ABI - Vyper overloads all share the single selector name
// 'get_blockhash', disambiguated only by argument types. Left as generated,
// encodeFunctionData/decodeFunctionResult throw for the two overloads that
// take arguments. This also adds an optional `callBlockNumber` param (the
// eth_call block tag) to all three methods, defaulting to
// LAST_FINALIZED_BLOCK_NUMBER as before, instead of hardcoding it.
//
// callBlockNumber is typed as `typeof LAST_FINALIZED_BLOCK_NUMBER` (a
// protobuf BigIntJson shape, e.g. `{ absVal, sign }`), not `bigint` - that's
// what `EVMClient.callContract`'s `blockNumber` option actually expects.
// Callers who want a specific block should pass the SDK's own
// `bigintToProtoBigInt(n)` / `blockNumber(n)` helpers.
function patchMainnetBlockView(path: string): void {
  const src = readFileSync(path, 'utf8')

  if (src.includes('callBlockNumber')) {
    console.log(`Already patched, skipping: ${path}`)
    return
  }

  const patched = src
    .replace(/functionName: 'get_blockhash0' as const,/g, "functionName: 'get_blockhash' as const,")
    .replace(/functionName: 'get_blockhash1' as const,/g, "functionName: 'get_blockhash' as const,")
    .replace(
      '\nexport const MainnetBlockViewABI',
      '\ntype BlockNumberOption = typeof LAST_FINALIZED_BLOCK_NUMBER\n\nexport const MainnetBlockViewABI',
    )
    .replace(
      /\n(\s*)\): readonly \[bigint, `0x\$\{string\}`\] \{/g,
      '\n$1  callBlockNumber: BlockNumberOption = LAST_FINALIZED_BLOCK_NUMBER,\n$1): readonly [bigint, `0x${string}`] {',
    )
    .replace(/blockNumber: LAST_FINALIZED_BLOCK_NUMBER,/g, 'blockNumber: callBlockNumber,')

  if (
    patched === src ||
    patched.includes('get_blockhash0') ||
    patched.includes('get_blockhash1') ||
    !patched.includes('BlockNumberOption')
  ) {
    throw new Error(
      `Failed to patch ${path} — generator output shape may have changed; update generate-bindings.ts.`,
    )
  }

  writeFileSync(path, patched)
  console.log(`Patched: ${path}`)
}
