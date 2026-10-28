import { readFile, readdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const lock = JSON.parse(await readFile(path.join(root, 'package-lock.json'), 'utf8'))
const sections = ['Granger-OSINT web interface — third-party notices\nGenerated from the locked production dependency tree.\n\nshadcn/ui Button composition adaptation\nCopyright (c) 2023 shadcn\nMIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\nThe above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.']
for (const [location, metadata] of Object.entries(lock.packages)) {
  if (!location || metadata.dev) continue
  const folder = path.join(root, location)
  const pkg = JSON.parse(await readFile(path.join(folder, 'package.json'), 'utf8'))
  const files = (await readdir(folder)).filter(name => /^(licen[cs]e|copying|notice)(\.|$)/i.test(name))
  const licenseTexts = await Promise.all(files.map(name => readFile(path.join(folder, name), 'utf8').catch(() => '')))
  sections.push(`${pkg.name}@${pkg.version}\nLicense: ${typeof pkg.license === 'string' ? pkg.license : JSON.stringify(pkg.license || metadata.license || 'See package source')}\n${typeof pkg.repository === 'string' ? pkg.repository : pkg.repository?.url || ''}\n\n${licenseTexts.join('\n\n') || 'License designation above is from package metadata; see the package repository.'}`)
}
const text = sections.join('\n\n' + '='.repeat(72) + '\n\n') + '\n'
await writeFile(path.join(root, 'public', 'THIRD_PARTY_NOTICES.txt'), text, 'utf8')
await writeFile(path.join(root, 'THIRD_PARTY_NOTICES.txt'), text, 'utf8')
