// GrangerPet JSON bridge to the installed PhoneInfoga source tree.
// Build from phoneinfoga-master using: go build -mod=readonly -o <output.exe> <this-file>
// No PhoneInfoga source is copied into this repository's executable.
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "os"

    "github.com/sundowndev/phoneinfoga/v2/lib/number"
    "github.com/sundowndev/phoneinfoga/v2/lib/remote"
)

type request struct {
    Query struct { Text string `json:"text"` } `json:"query"`
}

func emit(status string, results []map[string]interface{}, message string) {
    json.NewEncoder(os.Stdout).Encode(map[string]interface{}{
        "event": "final", "outcome": map[string]interface{}{
            "source": "phoneinfoga", "status": status, "results": results,
            "checked": 1, "message": message,
        },
    })
}

func main() {
    var input request
    if err := json.NewDecoder(io.LimitReader(os.Stdin, 100000)).Decode(&input); err != nil {
        emit("error", []map[string]interface{}{}, "Некорректный запрос номера.")
        return
    }
    n, err := number.NewNumber(input.Query.Text)
    if err != nil || !n.Valid {
        emit("empty", []map[string]interface{}{}, "Номер не прошёл проверку формата и плана нумерации.")
        return
    }
    raw, err := remote.NewLocalScanner().Run(*n, remote.ScannerOptions{})
    if err != nil {
        emit("error", []map[string]interface{}{}, "Локальная проверка номера не выполнена.")
        return
    }
    result := map[string]interface{}{
        "id": n.E164, "title": n.International, "type": "phone_metadata", "platform": "План нумерации",
        "url": "", "description": fmt.Sprintf("Страна/регион нумерации: %s. Это данные формата номера, а не сведения о владельце или текущем местоположении.", n.Country),
        "details": raw, "status": "metadata", "sources": []string{"phoneinfoga"},
    }
    emit("complete", []map[string]interface{}{result}, "Офлайн-данные PhoneInfoga. Сервисы с ключами не подключены.")
}
