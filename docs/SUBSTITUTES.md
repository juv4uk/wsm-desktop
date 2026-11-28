# Субститути WSM: статичний кеш без сервера

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **скрипт і схема готові, публікація не запускалася**
- Ключ підпису: **не створений** — його мусить створити власник
- Скрипт: [`scripts/narinfo_to_release_urls.py`](../scripts/narinfo_to_release_urls.py)

## Задача

Користувач має отримувати зібрані пакети каналу `wsm` як substitutes, а не збирати їх із джерел. Для цього потрібен сервер, який віддає формат Nix binary cache: `nix-cache-info`, `*.narinfo`, `nar/*.nar.zst`, `signing-key.pub`.

Тримаємо його без окремого хоста.

## Чому не «все в gh-pages» і не «все в git»

Дві половини кешу мають різний профіль розміру:

| Половина | Розмір | Змінюється |
| --- | --- | --- |
| метадані (`nix-cache-info`, `*.narinfo`, ключ) | кілобайти на запис | часто |
| архіви (`nar/*.nar.zst`) | десятки–сотні МБ | ніколи після публікації |

- **Усе в gh-pages** упирається в ліміт сайту **1 ГБ**: один closure з Qt/Plasma його перевищує.
- **Усе в git** упирається в **100 МБ на файл** — це ліміт Git і GitHub, а не Pages.
- **`git push --force`** не повертає місце: старі обʼєкти лишаються в репозиторії до збирання сміття на боці GitHub. Він зменшує розмір checkout-у, не сховища.

## Схема

```
архіви  → GitHub Release asset (до 2 ГБ на файл)
метадані → гілка gh-pages (кілобайти)
```

`scripts/narinfo_to_release_urls.py` переписує поле `URL:` у кожному `.narinfo` так, щоб воно вказувало на release asset.

**Підпис від цього не ламається.** Guix підписує відбиток із шляху в store, `NarHash`, `NarSize` і `References` — поля `URL` у ньому немає. Тому переписати `URL` безпечно, а `NarHash` — ні. Скрипт це перевіряє й відмовляється писати файл, якщо змінився хоч один підписаний рядок.

## Порядок

```sh
# 1. ключ підпису — створює ВЛАСНИК, не агент
sudo guix archive --generate-key

# 2. зібрати пакети каналу
guix build wsm-tools --no-substitutes

# 3. прогріти кеш: guix publish лінивий і не створює файли сам
guix publish --cache=/var/cache/publish --port=3000 &
for path in $(guix build wsm-tools --no-substitutes); do
  hash=$(basename "$path" | cut -d- -f1)
  curl -sf "http://localhost:3000/$hash.narinfo" > /dev/null
done

# 4. переписати URL на release assets
python3 scripts/narinfo_to_release_urls.py \
  --source /var/cache/publish --destination ./site \
  --base-url "https://github.com/juv4uk/wsm-desktop/releases/download/substitutes"

# 5. викласти ./site у gh-pages, архіви — у реліз
```

Крок 3 — неочевидний: `guix publish` генерує `.narinfo` і `.nar` **на запит**, тому без прогріву каталог кешу порожній.

## Для користувача

```sh
wget https://juv4uk.github.io/wsm-desktop/signing-key.pub -O wsm.pub
sudo guix archive --authorize < wsm.pub

guix build wsm-tools \
  --substitute-urls="https://juv4uk.github.io/wsm-desktop https://ci.guix.gnu.org"
```

Офіційний `ci.guix.gnu.org` лишається в списку: наш кеш покриває тільки пакети каналу.

## Що тут не вирішено

- **Ключ не створений.** Агент не має генерувати ключ підпису від імені власника — це рівносильно підписуванню чужих бінарників його імʼям.
- **Публікація не запускалася.** У середовищі немає Guix, тому перевірено лише переписування URL
  і структуру workflow, а не весь ланцюг.
- **Ключ у секреті.** Workflow `.github/workflows/substitutes.yml` бере `GUIX_SIGNING_KEY` із секретів
  репозиторію і падає з поясненням, якщо його немає. Непідписаний кеш користувач не зможе
  авторизувати, тому публікувати його було б марною роботою.
- **Політика GitHub Pages** дозволяє статичний хостинг, але не «bulk hosting». Метадані кешу — це кілобайти й нормальне використання; архіви навмисно винесені в релізи, щоб не наближатися до межі.
