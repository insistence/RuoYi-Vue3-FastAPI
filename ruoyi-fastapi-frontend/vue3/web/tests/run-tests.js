import { readdirSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const currentDirectory = dirname(fileURLToPath(import.meta.url))
const requestedSuite = process.argv[2]
const testRoot = requestedSuite ? join(currentDirectory, requestedSuite) : currentDirectory

function collectTestFiles(root) {
  const files = []
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const entryPath = join(root, entry.name)
    if (entry.isDirectory()) files.push(...collectTestFiles(entryPath))
    if (entry.isFile() && entry.name.endsWith('.test.js')) files.push(entryPath)
  }
  return files.sort()
}

const testFiles = collectTestFiles(testRoot)
if (testFiles.length === 0) throw new Error('No frontend tests found')

for (const testFile of testFiles) {
  await import(pathToFileURL(testFile).href)
  console.log(`ok ${relative(currentDirectory, testFile)}`)
}

console.log(`Frontend tests passed: ${testFiles.length}`)
