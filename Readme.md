# Pre-req

Install Xcode

``` xcode-select --install ```

Install brew 

``` /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" ```


Add Homebrew to PATH:
```
echo >> /Users/admin/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/admin/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

# Clone the Repo
 ```
 git clone https://github.com/techize/sre-mac-setup.git

 ```

# Run the script
```
cd sre-mac-setup
chmod +x sre-tools-mac.sh
./sre-tools-mac.sh

```
# Package Links

## Text and Collaboration Tools
- [Visual Studio Code](https://formulae.brew.sh/cask/visual-studio-code)
- [GitHub](https://formulae.brew.sh/cask/github)
- [Notion](https://formulae.brew.sh/cask/notion)

## Cloud CLI
- [Google Cloud SDK](https://formulae.brew.sh/cask/google-cloud-sdk)
- [AWS CLI](https://formulae.brew.sh/formula/awscli)

## Kubernetes and Containers
- [Rancher](https://formulae.brew.sh/cask/rancher)
- [Kubernetes CLI](https://formulae.brew.sh/formula/kubernetes-cli)
- [Kubectx](https://formulae.brew.sh/formula/kubectx)
- [K9s](https://formulae.brew.sh/formula/k9s)

## DevOps
- [Argo CD](https://formulae.brew.sh/formula/argocd)
- [Helm](https://formulae.brew.sh/formula/helm)
- [tfenv](https://formulae.brew.sh/formula/tfenv)
- [tgenv](https://formulae.brew.sh/formula/tgenv)
- [jenv](https://formulae.brew.sh/formula/jenv)
- [Go](https://formulae.brew.sh/formula/go)

## Other
- [iTerm2](https://formulae.brew.sh/cask/iterm2)
- [Powerlevel10k](https://github.com/romkatv/powerlevel10k)
```
brew install romkatv/powerlevel10k/powerlevel10k
echo "source $(brew --prefix)/opt/powerlevel10k/powerlevel10k.zsh-theme" >>~/.zshrc
```
- [jq](https://formulae.brew.sh/formula/jq)
- [wget](https://formulae.brew.sh/formula/wget)
- [tree](https://formulae.brew.sh/formula/tree)
- [Adobe Acrobat Reader](https://formulae.brew.sh/cask/adobe-acrobat-reader)
- [Bash](https://formulae.brew.sh/formula/bash)
- [Asciinema](https://formulae.brew.sh/formula/asciinema)
- [Wireshark](https://formulae.brew.sh/cask/wireshark)
- [The Unarchiver](https://formulae.brew.sh/cask/the-unarchiver)
- [1Password](https://formulae.brew.sh/cask/1password)


