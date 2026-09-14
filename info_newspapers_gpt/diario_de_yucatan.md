# Diario de Yucatan

Research date: 2026-08-10

## Suggested Workbook Metadata

| Field | Suggested value |
| --- | --- |
| name.page | Diario de Yucatan / El Diario de Yucatan |
| official_name | Diario de Yucatan |
| tagline | El periodico de la vida peninsular |
| owner_group / media_group | Grupo Megamedia |
| legal_name | Compania Tipografica Yucateca, S.A. de C.V.; also listed among Megamedia Integradora, S.A. de C.V. and its integrated companies |
| director_general | Carlos R. Menendez Losa, per current directory |
| director_editorial | Luis Alberto Gonzalez Uribe, per current directory |
| subdirector_editorial / editor_digital_en_jefe | Juan Carlos Gongora Solis, per current directory |
| director_medios_tradicionales | Olegario Manuel Moguel Bernal |
| state | Yucatan |
| municipality | Merida |
| city | Merida |
| address | Calle 60 No. 521 entre 65 y 67, Centro, CP 97000, Merida, Yucatan |
| coverage_scope | Peninsular/regional, especially Yucatan, with national/international coverage |
| year_founded | 1925 |
| founding_date | 1925-05-31 |
| founder | Carlos R. Menendez Gonzalez |
| predecessor_context | Roots in La Revista de Merida and La Revista de Yucatan |
| media_type | periodico |
| platform | print, digital, video/social |
| periodicity | daily |
| subscription | 0 in workbook, but current site has subscription/digital edition products; verify coding meaning |
| scrapped | 1 for row 7 / yucatan_yucatan; duplicate row 71 is marked 0 |
| folder_name | yucatan / yucatan_yucatan |
| file_name | articles.parquet |
| ideology.subjective | conservative / regionalist / historically anti-PRI and PAN-adjacent |
| ideology_confidence | medium-high for historical ideology; medium for current alignment |

## Workbook / Deduplication Note

The workbook has two apparent Diario de Yucatan entries using the same URL and social channels:

- Row 7: `El Diario de Yucatan`, owner/comsoc listed as `EDICION Y PUBLICIDAD DE MEDIOS DE LOS ESTADOS, S. DE R.L. DE C.V.`, scraped = 1, folder `yucatan`.
- Row 71: `Diario de Yucatan`, owner/comsoc listed as `COMPANIA TIPOGRAFICA YUCATECA, S.A. DE C.V. / DIARIO DE YUCATAN`, scraped = 0.

Official/legal sources point more strongly to Grupo Megamedia / Compania Tipografica Yucateca, S.A. de C.V. for Diario de Yucatan. The EPME value in row 7 may reflect a COMSOC/transcript mapping or an association with state editors, but it should be checked before using it as the owner/legal entity. Recommended action: merge or reconcile the duplicate rows and keep Compania Tipografica Yucateca / Grupo Megamedia as the outlet legal/media-family metadata.

## Notes

Diario de Yucatan is one of the oldest and most influential regional newspapers in Mexico. Its own anniversary material and the Library of Congress record place the beginning of publication on May 31, 1925. The founder was Carlos R. Menendez Gonzalez.

The current official directory lists Carlos R. Menendez Losa as director general, Luis Alberto Gonzalez Uribe as director editorial, Juan Carlos Gongora Solis as subdirector editorial and editor digital en jefe, and Olegario Manuel Moguel Bernal as director of traditional media.

The privacy notice identifies Grupo Megamedia and its integrated companies, including Compania Tipografica Yucateca, S.A. de C.V., and gives a Merida address. The current contact page gives Calle 60 No. 521 entre 65 y 67, Col. Centro, CP 97000, Merida, Yucatan.

For ideology, use a cautious but meaningful label. Academic/historical sources describe Diario de Yucatan as Catholic/conservative, regionalist, anti-centralist and historically anti-PRI, with influence in the growth of PAN support in Yucatan. A 2015 Scielo article states that the newspaper historically defended hacendado interests, had Catholic tendencies, and opposed agrarian reform. A UADY history/culture page describes it as a Catholic and conservative opinion-making newspaper in the southeast and close to PAN-oriented anti-PRI regional politics. For current coding, `conservative / regionalist / historically anti-PRI and PAN-adjacent` is stronger than simply `opp`.

## Source URLs

- Official directory: https://www.yucatan.com.mx/directorio
- Official contact page: https://www.yucatan.com.mx/contacto
- Official privacy notice / Grupo Megamedia and integrated companies: https://www.yucatan.com.mx/aviso-de-privacidad
- Official anniversary tag / founding summary: https://www.yucatan.com.mx/etiqueta/aniversario-del-diario
- Diario de Yucatan digital edition "Nosotros": https://www.dydigital.com.mx/
- SIC record for Diario de Yucatan: https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=306
- Library of Congress record: https://www.loc.gov/item/sn90048502/
- Scielo article on press freedom and the 1931-1933 amparo: https://www.scielo.org.mx/scielo.php?pid=S1870-719X2015000100007&script=sci_arttext
- UADY page on Yucatan identity/culture and PAN support: https://www.mayas.uady.mx/historia/cont_01.html
- Current editorial section, useful for current political-line checks: https://www.yucatan.com.mx/seccion/editorial
